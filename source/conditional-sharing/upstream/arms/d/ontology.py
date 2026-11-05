"""Ordered predicate signatures from the D mapping-rule Turtle subset.

No RDF dependency is installed by docker/Dockerfile. Supported Turtle: @prefix,
IRIs, prefixed names, a, JSON-style strings, integers/booleans, blank-node property
lists, and ;/, abbreviation. Other Turtle constructs fail explicitly.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import re

RULE = 'http://ai.uos.ac.kr/rule#'
RDF = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
XSD = 'http://www.w3.org/2001/XMLSchema#'


@dataclass(frozen=True)
class Argument:
    name: str
    argument_type: str


@dataclass(frozen=True)
class Predicate:
    name: str
    arguments: tuple[Argument, ...]
    namespace: str = ""
    domain: str = ""


_TOKEN = re.compile(r'\s+|\#[^\n]*|<[^>]*>|"(?:[^"\\]|\\.)*"|@prefix|[A-Za-z_][\w-]*:[\w-]*|:[\w-]*|-?\d+|[A-Za-z_][\w-]*|[\[\];,.]')


def tokens(text, pattern=_TOKEN):
    out, pos = [], 0
    while pos < len(text):
        m = pattern.match(text, pos)
        if not m:
            raise ValueError(f'unsupported syntax at offset {pos}: {text[pos:pos+40]!r}')
        t = m.group()
        if not t.isspace() and not t.startswith('#'):
            out.append(t)
        pos = m.end()
    return out


class Turtle:
    def __init__(self, text):
        self.ts = tokens(text)
        self.i = 0
        self.prefixes = {}
        self.triples = []
        self.blank = 0

    def pop(self, expected=None):
        if self.i == len(self.ts):
            raise ValueError('unexpected end of Turtle')
        t = self.ts[self.i]
        self.i += 1
        if expected is not None and t != expected:
            raise ValueError(f'expected {expected}, got {t}')
        return t

    def term(self):
        t = self.pop()
        if t == '[':
            self.blank += 1
            node = ('blank', self.blank)
            self.properties(node)
            self.pop(']')
            return node
        if t.startswith('"'):
            return ('literal', json.loads(t))
        if t.startswith('<'):
            return t[1:-1]
        if t == 'a':
            return RDF + 'type'
        if t in ('true', 'false') or re.fullmatch(r'-?\d+', t):
            return ('literal', json.loads(t))
        if ':' in t:
            p, local = t.split(':', 1)
            if p not in self.prefixes:
                raise ValueError(f'undefined Turtle prefix {p}')
            return self.prefixes[p] + local
        raise ValueError(f'unsupported Turtle term {t}')

    def properties(self, subject):
        while True:
            pred = self.term()
            while True:
                self.triples.append((subject, pred, self.term()))
                if self.ts[self.i] != ',':
                    break
                self.pop(',')
            if self.ts[self.i] != ';':
                return
            self.pop(';')
            if self.ts[self.i] in (']', '.'):
                return

    def parse(self):
        while self.i < len(self.ts):
            if self.ts[self.i] == '@prefix':
                self.pop()
                prefix = self.pop()
                uri = self.pop()
                if not prefix.endswith(':') or not uri.startswith('<'):
                    raise ValueError('bad Turtle prefix declaration')
                self.prefixes[prefix[:-1]] = uri[1:-1]
            else:
                self.properties(self.term())
            self.pop('.')
        return self

    def values(self, subject, predicate):
        return [o for s, p, o in self.triples if s == subject and p == predicate]

    def one(self, subject, predicate):
        vals = self.values(subject, predicate)
        if len(vals) != 1:
            raise ValueError(f'expected exactly one {predicate} for {subject}')
        return vals[0]


def parse_ontology(text, domain=""):
    g = Turtle(text).parse()
    if '' not in g.prefixes:
        raise ValueError('ontology requires a default namespace')
    namespace = g.prefixes['']
    def literal(s, p):
        v = g.one(s, p)
        if not isinstance(v, tuple) or v[0] != 'literal':
            raise ValueError(f'expected literal for {p}')
        return v[1]
    def typed(s, t):
        if t not in g.values(s, RDF + 'type'):
            raise ValueError(f'{s} must be a {t}')
    predicates = {}
    for rule in dict.fromkeys(s for s, p, o in g.triples if p == RDF+'type' and o == RULE+'Rule'):
        name = literal(rule, RULE+'ruleName')
        body = g.one(rule, RULE+'hasBody')
        for pattern in g.values(body, RULE+'hasPattern'):
            typed(pattern, RULE+'TriplePattern')
            if type(literal(pattern, RULE+'isMutable')) is not bool:
                raise ValueError('isMutable must be boolean')
        head = g.one(rule, RULE+'hasHead')
        pattern = g.one(head, RULE+'hasPattern')
        typed(pattern, RULE+'PredicatePattern')
        if name != literal(pattern, RULE+'predicateName') or namespace + name in predicates:
            raise ValueError(f'duplicate or inconsistent predicate {name}')
        args = {}
        for arg in g.values(pattern, RULE+'hasArgument'):
            typed(arg, RULE+'Argument')
            i = literal(arg, RULE+'argumentIndex')
            if type(i) is not int or i < 0 or i in args:
                raise ValueError(f'invalid/duplicate argumentIndex {i}')
            var = g.one(arg, RULE+'hasTerm')
            typed(var, RULE+'Variable')
            vname = literal(var, RULE+'variableName')
            typ = g.one(arg, RULE+'argumentType')
            if not isinstance(vname, str) or not re.fullmatch(r'\?[A-Za-z_][A-Za-z0-9_]*', vname):
                raise ValueError(f'invalid variableName {vname}')
            if not isinstance(typ, str) or ':' not in typ:
                raise ValueError('argumentType must be an IRI')
            args[i] = Argument(vname[1:], typ)
        if not args or sorted(args) != list(range(len(args))):
            raise ValueError(f'{name}: argument indices must be contiguous starting at zero')
        ordered = tuple(args[i] for i in range(len(args)))
        if len({a.name for a in ordered}) != len(ordered):
            raise ValueError(f'{name}: duplicate argument names')
        predicates[namespace + name] = Predicate(name, ordered, namespace, domain)
    if not predicates:
        raise ValueError('ontology has no rules')
    return predicates


def load_ontology(path):
    path = Path(path)
    return parse_ontology(path.read_text(), path.stem)


def load_catalog():
    """Load all bundled ontologies, indexed by default namespace + predicateName."""
    catalog = {}
    for path in sorted((Path(__file__).parent / 'ontology').glob('*.ttl')):
        for uri, predicate in load_ontology(path).items():
            if uri in catalog:
                raise ValueError(f'duplicate predicate URI {uri}')
            catalog[uri] = predicate
    return catalog
