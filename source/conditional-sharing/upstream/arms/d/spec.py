"""D organization model loader and authoring serializers; legacy YAML API retained."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

OPS = ("<=", ">=", "!=", "=", "<", ">")
_COND = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(<=|>=|!=|=|<|>)\s*([^<>=!\s].*?)\s*$")


@dataclass(frozen=True)
class Cond:
    field: str
    op: str
    value: object

    def holds(self, v):
        x = v.get(self.field) if v is not None else None
        if x is None:
            return False
        try:
            return {"=": x == self.value, "!=": x != self.value, "<": x < self.value,
                    "<=": x <= self.value, ">": x > self.value, ">=": x >= self.value}[self.op]
        except TypeError:
            return False

    def text(self):
        return f"{self.field} {self.op} {self.value}"


@dataclass
class ReadDecl:
    context: str
    where: tuple[Cond, ...] = ()
    raw: object = None
    alternative_group: int | None = None


@dataclass
class RoleDecl:
    name: str
    reads: list[ReadDecl] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)
    change_patterns: list[ReadDecl] = field(default_factory=list)


@dataclass
class Spec:
    domain: str
    vocabulary: dict            # context -> {"key": str, "fields": {name: type}}
    roles: dict                 # role -> RoleDecl


@dataclass
class Binding:
    cfg: str
    agents: dict                # agent -> [role]


def parse_value(tok: str):
    t = tok.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "'\"":
        return t[1:-1]
    if re.fullmatch(r"-?\d+", t):
        return int(t)
    if t.lower() in ("true", "false"):
        return t.lower() == "true"
    return t


def parse_where(text) -> tuple[Cond, ...]:
    """'battery < 30 and zone = storage' -> (Cond, Cond). Raises ValueError on syntax errors."""
    if text is None or text == "":
        return ()
    parts = re.split(r"\s+and\s+", str(text).strip(), flags=re.IGNORECASE)
    out = []
    for p in parts:
        m = _COND.match(p)
        if not m:
            raise ValueError(f"bad condition: {p!r}")
        out.append(Cond(m.group(1), m.group(2), parse_value(m.group(3))))
    return tuple(out)


def load_spec_yaml_legacy(path) -> Spec:
    with open(path) as f:
        d = yaml.safe_load(f)
    return spec_from_dict(d)


def spec_from_dict(d) -> Spec:
    if d.get("schema") != "rcs-d-spec/1":
        raise ValueError(f"schema: {d.get('schema')}")
    roles = {}
    for name, body in (d.get("roles") or {}).items():
        ctx = (body or {}).get("context") or {}
        reads = []
        for r in ctx.get("reads") or []:
            if isinstance(r, str):
                reads.append(ReadDecl(r, (), r))
            else:
                reads.append(ReadDecl(r["name"], parse_where(r.get("where")), r))
        roles[name] = RoleDecl(name, reads, list(ctx.get("changes") or []))
    return Spec(d.get("domain", ""), d.get("vocabulary") or {}, roles)


def load_binding(path) -> Binding:
    with open(path) as f:
        d = yaml.safe_load(f)
    if d.get("schema") != "rcs-d-binding/1":
        raise ValueError(f"schema: {d.get('schema')}")
    return Binding(d["cfg"], {a: list(rs) for a, rs in (d.get("agents") or {}).items()})


# Compatibility only: existing phase-2 tools import this name.
load_spec = load_spec_yaml_legacy


class OrgError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(f'{code}: {message}')


_ORG_TOKEN = re.compile(r'\s+|\#[^\n]*|<[A-Za-z][A-Za-z0-9+.-]*:[^<>\s]*>|"(?:[^"\\]|\\.)*"|\$[A-Za-z_][A-Za-z0-9_]*|(?:[A-Za-z_][\w-]*)?:[\w]*|[A-Za-z_][\w]*|-?\d+(?:\.\d+)?|==|!=|<=|>=|\|\||&&|[{}(),;<>]')


class OrgParser:
    def __init__(self, text, predicates):
        from arms.d.ontology import tokens
        self.ts = tokens(text, _ORG_TOKEN)
        self.i = 0
        self.predicates = predicates
        self.group = 0
        self.prefixes = {}
        self.used = {}

    def peek(self):
        return self.ts[self.i] if self.i < len(self.ts) else None

    def pop(self, expected=None):
        t = self.peek()
        if t is None or (expected is not None and t != expected):
            raise OrgError('SYNTAX', f'expected {expected or "token"}, got {t!r} at token {self.i}')
        self.i += 1
        return t

    def identifier(self):
        t = self.pop()
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', t):
            raise OrgError('BAD_ID', f'invalid identifier {t}')
        return t

    def comparison(self, bound):
        import json
        var = self.pop()
        if var not in bound:
            raise OrgError('UNKNOWN_FIELD', f'unbound condition variable {var}')
        op = self.pop()
        if op not in ('==', '!=', '<', '<=', '>', '>='):
            raise OrgError('SYNTAX', f'invalid comparison operator {op}')
        tok = self.pop()
        if ':' in tok and not tok.startswith('"'):
            raise OrgError('TYPE_MISMATCH', 'ontology-class comparison not implemented')
        if not (tok.startswith('"') or tok in ('true', 'false') or re.fullmatch(r'-?\d+(?:\.\d+)?', tok)):
            raise OrgError('SYNTAX', f'expected a literal, got {tok}')
        value = json.loads(tok) if tok.startswith('"') or tok in ('true', 'false') else (float(tok) if '.' in tok else int(tok))
        return Cond(bound[var], '=' if op == '==' else op, value)

    def line(self, bound):
        # OR of conjunctions; && binds tighter. No parenthesized expressions.
        alts = [(self.comparison(bound),)]
        while self.peek() in ('&&', '||'):
            op = self.pop()
            c = self.comparison(bound)
            if op == '&&':
                alts[-1] += (c,)
            else:
                alts.append((c,))
        self.pop(';')
        return alts

    def pattern(self, conditions=True):
        token = self.pop()
        if not re.fullmatch(r'(?:[A-Za-z_][\w-]*)?:[A-Za-z_][\w]*', token):
            raise OrgError('BAD_ID', f'predicate must be a prefixed name: {token}')
        prefix, local = token.split(':', 1)
        if prefix not in self.prefixes:
            raise OrgError('UNDECLARED_PREFIX', f'undeclared prefix {prefix!r}')
        uri = self.prefixes[prefix] + local
        if uri not in self.predicates:
            raise OrgError('UNKNOWN_CONTEXT', f'unknown predicate URI {uri}')
        name = self.predicates[uri].name
        if name in self.used and self.used[name] != uri:
            raise OrgError('AMBIGUOUS_CONTEXT', f'local predicate name {name} used from multiple namespaces')
        self.used[name] = uri
        self.pop('(')
        variables = []
        if self.peek() != ')':
            while True:
                v = self.pop()
                if not v.startswith('$'):
                    raise OrgError('SYNTAX', f'expected pattern variable, got {v}')
                variables.append(v)
                if self.peek() != ',':
                    break
                self.pop(',')
        self.pop(')')
        args = self.predicates[uri].arguments
        if len(variables) != len(args):
            raise OrgError('ARITY_MISMATCH', f'{name} expects {len(args)} arguments, got {len(variables)}')
        if len(set(variables)) != len(variables):
            raise OrgError('BAD_ID', 'repeated pattern variables are not supported')
        bound = {v: a.name for v, a in zip(variables, args)}
        alts = [()]
        if self.peek() == '{':
            if not conditions:
                raise OrgError('SYNTAX', f'changes pattern {name} takes no condition block')
            self.pop('{')
            while self.peek() != '}':
                line = self.line(bound)
                alts = [a + b for a in alts for b in line]
            self.pop('}')
        else:
            self.pop(';')
        self.group += 1
        return [ReadDecl(name, a, None, self.group) for a in alts]

    def parse(self):
        roles = {}
        while self.peek() == 'prefix':
            self.pop('prefix')
            prefix = self.pop()
            uri = self.pop()
            if not re.fullmatch(r'(?:[A-Za-z_][\w-]*)?:', prefix) or not uri.startswith('<') or not uri.endswith('>'):
                raise OrgError('SYNTAX', 'invalid prefix declaration')
            if prefix[:-1] in self.prefixes:
                raise OrgError('BAD_ID', f'duplicate prefix {prefix}')
            self.prefixes[prefix[:-1]] = uri[1:-1]
            self.pop(';')
        while self.peek() is not None:
            self.pop('role')
            name = self.identifier()
            if name in roles:
                raise OrgError('BAD_ID', f'duplicate role {name}')
            role = RoleDecl(name)
            self.pop('{')
            sections = set()
            while self.peek() != '}':
                section = self.pop()
                if section not in ('reads', 'changes') or section in sections:
                    raise OrgError('SYNTAX', f'invalid/duplicate section {section}')
                sections.add(section)
                self.pop('{')
                while self.peek() != '}':
                    patterns = self.pattern(conditions=section == 'reads')
                    if section == 'reads':
                        role.reads.extend(patterns)
                    else:
                        role.changes.append(patterns[0].context)
                        role.change_patterns.extend(patterns)
                self.pop('}')
            self.pop('}')
            roles[name] = role
        return roles


def parse_org(text, predicates):
    parser = OrgParser(text, predicates)
    roles = parser.parse()
    used = {name: predicates[uri] for name, uri in parser.used.items()}
    namespaces = {p.namespace for p in used.values()}
    # Preserve all keys from participating ontologies for byte-compatible output.
    # Explicitly used predicates take precedence over unused namesakes.
    selected = {}
    for p in predicates.values():
        if p.namespace in namespaces:
            selected.setdefault(p.name, used.get(p.name, p))
    vocabulary = {name: {'key': p.arguments[0].name,
                         'key_type': p.arguments[0].argument_type,
                         'fields': {a.name: a.argument_type for a in p.arguments[1:]}}
                  for name, p in selected.items()}
    domains = sorted({p.domain for p in used.values() if p.domain})
    return Spec(','.join(domains), vocabulary, roles)


def load_spec_org(path, catalog=None):
    from pathlib import Path
    from arms.d.ontology import load_catalog
    return parse_org(Path(path).read_text(), load_catalog() if catalog is None else catalog)


@dataclass
class OrgPattern:
    predicate: str
    variables: list[str]
    conditions: list[list[str]] = field(default_factory=list)


@dataclass
class OrgDocument:
    """Editable syntax, before ontology validation (also represents injected defects)."""
    prefixes: dict
    roles: dict


class OrgSyntaxParser(OrgParser):
    """Reuse the org lexer/cursor without resolving predicates or bound variables."""
    def parse(self):
        prefixes, roles = {}, {}
        while self.peek() == 'prefix':
            self.pop('prefix')
            prefix, uri = self.pop(), self.pop()
            if prefix[:-1] in prefixes:
                raise OrgError('BAD_ID', 'duplicate prefix')
            prefixes[prefix[:-1]] = uri[1:-1]
            self.pop(';')
        while self.peek() is not None:
            self.pop('role')
            name = self.identifier()
            if name in roles:
                raise OrgError('BAD_ID', 'duplicate role')
            sections = roles[name] = {}
            self.pop('{')
            while self.peek() != '}':
                section = self.pop()
                if section not in ('reads', 'changes') or section in sections:
                    raise OrgError('SYNTAX', 'invalid/duplicate section')
                patterns = sections[section] = []
                self.pop('{')
                while self.peek() != '}':
                    predicate = self.pop()
                    self.pop('(')
                    variables = []
                    while self.peek() != ')':
                        variables.append(self.pop())
                        if self.peek() != ')':
                            self.pop(',')
                    self.pop(')')
                    conditions = []
                    if self.peek() == '{':
                        self.pop('{')
                        while self.peek() != '}':
                            line = []
                            while self.peek() != ';':
                                line.append(self.pop())
                            self.pop(';')
                            conditions.append(line)
                        self.pop('}')
                    else:
                        self.pop(';')
                    patterns.append(OrgPattern(predicate, variables, conditions))
                self.pop('}')
            self.pop('}')
        return OrgDocument(prefixes, roles)


def parse_org_document(text):
    return OrgSyntaxParser(text, {}).parse()


def serialize_org(doc):
    """Canonical editable org serialization; preserves statements, OR and invalid names.

    Unlike load_spec_org this intentionally does not validate against the ontology:
    defect injection and repair accounting must retain invalid input verbatim in meaning.
    """
    lines = [f'prefix {p}: <{uri}>;' for p, uri in doc.prefixes.items()]
    for name, sections in doc.roles.items():
        lines += ['', f'role {name} {{']
        for section, patterns in sections.items():
            lines.append(f'  {section} {{')
            for pattern in patterns:
                line = f"    {pattern.predicate}({', '.join(pattern.variables)})"
                if pattern.conditions:
                    lines += [line + ' {', *['      ' + ' '.join(c) + ';' for c in pattern.conditions], '    }']
                else:
                    lines.append(line + ';')
            lines.append('  }')
        lines.append('}')
    return '\n'.join(lines) + '\n'


def org_text(spec):
    import json
    lines = [f'prefix {spec.domain}: <http://ai.uos.ac.kr/{spec.domain}-ontology#>;', '']
    def pattern(name, where=()):
        v = spec.vocabulary[name]
        args = [v['key'], *v['fields']]
        line = f"    {spec.domain}:{name}({', '.join('$' + a for a in args)})"
        if not where:
            return [line + ';']
        return [line + ' {', *[f'      ${c.field} {"==" if c.op == "=" else c.op} {json.dumps(c.value, ensure_ascii=False)};' for c in where], '    }']
    for role in spec.roles.values():
        lines += [f'role {role.name} {{', '  reads {']
        for rd in role.reads:
            lines += pattern(rd.context, rd.where)
        lines += ['  }', '  changes {']
        for name in role.changes:
            lines += pattern(name)
        lines += ['  }', '}', '']
    return '\n'.join(lines)
