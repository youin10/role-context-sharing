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
RDFS = 'http://www.w3.org/2000/01/rdf-schema#'
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


def load_catalog(directory=None):
    """Load all ontologies of `directory` (default: bundled), indexed by default namespace + predicateName."""
    catalog = {}
    for path in sorted(Path(directory or Path(__file__).parent / 'ontology').glob('*.ttl')):
        for uri, predicate in load_ontology(path).items():
            if uri in catalog:
                raise ValueError(f'duplicate predicate URI {uri}')
            catalog[uri] = predicate
    return catalog


class TypeRegistry:
    """Class hierarchy (rdfs:subClassOf) and individual types (rdf:type), fixed during a run.

    Kept apart from the predicate signatures: an argumentType says what kind of entity an
    argument position takes; whether individual `biped1` is a Biped is a separate fact here.
    Membership includes subclasses (transitive subClassOf, author decision 2026-10-28); no
    other inference (no equivalence, disjointness or dynamic retyping).
    """

    def __init__(self, classes, parents, individuals, namespace):
        self.classes = set(classes)              # class URIs
        self.parents = parents                   # class URI -> set of direct superclass URIs
        self.individuals = individuals           # individual ID -> set of direct class URIs
        self.namespace = namespace
        self._sup = {}
        for c in self.classes:
            self.superclasses(c)

    def superclasses(self, c, path=()):
        """c and every class above it (reflexive, transitive)."""
        if c in self._sup:
            return self._sup[c]
        if c in path:
            raise ValueError(f'subClassOf cycle through {c}')
        out = {c}
        for p in self.parents.get(c, ()):
            out |= self.superclasses(p, path + (c,))
        self._sup[c] = frozenset(out)
        return self._sup[c]

    def is_subclass(self, sub, sup):
        return sup in self.superclasses(sub)

    def compatible(self, a, b):
        """Can a value of class a also be of class b under the fixed catalogue? True when some
        declared class is below both (a subclass relation is the special case) or some registered
        individual belongs to both. Closed over this catalogue; not OWL disjointness reasoning."""
        if any(a in self.superclasses(k) and b in self.superclasses(k) for k in self.classes):
            return True
        return any({a, b} <= self.types_of(i) for i in self.individuals)

    def types_of(self, individual):
        """Every class the individual belongs to; KeyError for an unregistered individual."""
        out = set()
        for c in self.individuals[individual]:
            out |= self.superclasses(c)
        return out

    def closure_table(self):
        return {i: sorted(self.types_of(i)) for i in sorted(self.individuals)}


def load_types(*paths):
    """Turtle files with `C a rdfs:Class`, `C rdfs:subClassOf D` and `:id a C` (individual IDs are
    local names in the default namespace). An undeclared class or a cycle is an error."""
    triples, namespace = [], None
    for path in paths:
        g = Turtle(Path(path).read_text()).parse()
        if '' not in g.prefixes:
            raise ValueError(f'{path}: types require a default namespace')
        if namespace not in (None, g.prefixes['']):
            raise ValueError('type files must share one default namespace')
        namespace = g.prefixes['']
        triples += g.triples
    classes = {s for s, p, o in triples if p == RDF + 'type' and o == RDFS + 'Class'}
    parents, individuals = {}, {}
    for s, p, o in triples:
        if p == RDFS + 'subClassOf':
            if s not in classes or o not in classes:
                raise ValueError(f'subClassOf between undeclared classes {s} {o}')
            parents.setdefault(s, set()).add(o)
        elif p == RDF + 'type' and o != RDFS + 'Class':
            if o not in classes:
                raise ValueError(f'{s} has undeclared type {o}')
            if not isinstance(s, str) or not s.startswith(namespace):
                raise ValueError(f'individual {s} is not in the default namespace')
            individuals.setdefault(s[len(namespace):], set()).add(o)
        elif p not in (RDF + 'type',):
            raise ValueError(f'unsupported type triple predicate {p}')
    return TypeRegistry(classes, parents, individuals, namespace)


def value_error(atype, v, types):
    """Why v is not a value of argumentType atype: (code, message), or None."""
    if atype == XSD + "integer":
        ok = type(v) is int
    elif atype in (XSD + "decimal", XSD + "float", XSD + "double"):
        ok = type(v) in (int, float)
    elif atype == XSD + "string":
        ok = isinstance(v, str)
    elif atype == XSD + "boolean":
        ok = type(v) is bool
    elif types is not None and atype in types.classes:
        if not isinstance(v, str) or v not in types.individuals:
            return "UNKNOWN_INDIVIDUAL", f"{v!r} is not a registered individual"
        ok = atype in types.types_of(v)
        if not ok:
            return "TYPE_MISMATCH", f"individual {v!r} is not a {atype}"
    else:
        return "UNKNOWN_TYPE", f"argumentType {atype} has no value check"
    return None if ok else ("TYPE_MISMATCH", f"{v!r} is not a {atype}")


def report_error(signature, types, context, instance, op, value):
    """Check one producer report against the known entity catalogue (predicate signatures +
    fixed individual types). Shared by the D SM and the A baseline helper. (code, message) or None."""
    s = signature.get(context)
    if s is None:
        return "UNKNOWN_CONTEXT", f"context {context} has no signature"
    err = value_error(s["key_type"], instance, types)
    if err:
        return err[0], f"instance: {err[1]}"
    if op == "delete":
        return None
    if not isinstance(value, dict) or set(value) != set(s["fields"]):
        return "BAD_FIELDS", f"fields {sorted(value) if isinstance(value, dict) else value!r} != {sorted(s['fields'])}"
    for f, atype in s["fields"].items():
        err = value_error(atype, value[f], types)
        if err:
            return err[0], f"{f}: {err[1]}"
    return None


def signature_of(catalog, namespace=None):
    """{context: {key, key_type, fields}} from predicate signatures (argument order kept)."""
    return {p.name: {"key": p.arguments[0].name, "key_type": p.arguments[0].argument_type,
                     "fields": {a.name: a.argument_type for a in p.arguments[1:]}}
            for p in catalog.values() if namespace is None or p.namespace == namespace}
