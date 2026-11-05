"""GL (Generalized List) and LTM subscription rules for baseline A (spec 비교군 A, ARBI README
"GL", "LTM Interface"). Re-implemented from the README description; no ARBI code is used.

  GL      (name expr ...) with expr = "string" | int | float | $variable | symbol | GL
  rule    (rule (fact (<Ctx> $<key> $<f1> ...)) [(<op> $<field> <const>)]* --> (notify (<Ctx> $<key> $<f1> ...)))
          op in < <= > >= = != ; several conditions are a conjunction (brief §18-2).
A context fact is (<Ctx> "<instance>" <v1> ...) with the value fields in the order of the public
context table; booleans are GL ints 1 / 0 (README: Int also stands for true / false).
A deletion is the tombstone fact (deleted (<Ctx> "<instance>")) (spec A-2-4, variant A only).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

_TOKEN = re.compile(r'\s*(?:(\()|(\))|("(?:[^"\\]|\\.)*")|([^\s()"]+))')
OPS = {"<": lambda a, b: a < b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b, ">=": lambda a, b: a >= b,
       "=": lambda a, b: a == b, "!=": lambda a, b: a != b}


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class Sym:
    name: str


def parse(text):
    """GL text -> nested tuples of str | int | float | Var | Sym."""
    toks, pos, stack, out = [], 0, [], None
    text = text.strip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise ValueError(f"bad GL near {text[pos:pos + 20]!r}")
        pos = m.end()
        toks.append(m.groups())
    for lp, rp, s, atom in toks:
        if lp:
            stack.append([])
        elif rp:
            if not stack:
                raise ValueError("unbalanced ')'")
            gl = tuple(stack.pop())
            if stack:
                stack[-1].append(gl)
            elif out is None:
                out = gl
            else:
                raise ValueError("more than one top-level GL")
        else:
            if not stack:
                raise ValueError("value outside a GL")
            stack[-1].append(json.loads(s) if s else _atom(atom))
    if stack or out is None:
        raise ValueError("unbalanced '('")
    return out


def _atom(a):
    if a.startswith("$"):
        return Var(a[1:])
    try:
        return int(a)
    except ValueError:
        pass
    try:
        return float(a)
    except ValueError:
        return Sym(a)


def fmt(x):
    if isinstance(x, tuple):
        return "(" + " ".join(fmt(e) for e in x) + ")"
    if isinstance(x, Var):
        return "$" + x.name
    if isinstance(x, Sym):
        return x.name
    if isinstance(x, str):
        return json.dumps(x)
    return str(x)


def unify(pattern, fact, b):
    """Bindings extended so that pattern = fact, or None."""
    if isinstance(pattern, Var):
        if pattern.name in b:
            return b if b[pattern.name] == fact else None
        return {**b, pattern.name: fact}
    if isinstance(pattern, tuple):
        if not isinstance(fact, tuple) or len(pattern) != len(fact):
            return None
        for p, f in zip(pattern, fact):
            b = unify(p, f, b)
            if b is None:
                return None
        return b
    return b if pattern == fact and isinstance(pattern, Sym) == isinstance(fact, Sym) else None


def subst(t, b):
    if isinstance(t, Var):
        return b.get(t.name, t)
    if isinstance(t, tuple):
        return tuple(subst(e, b) for e in t)
    return t


@dataclass(frozen=True)
class Rule:
    text: str
    fact: tuple                 # (Ctx $key $f1 ...)
    conds: tuple                # ((op, var, const), ...)
    notify: tuple

    @staticmethod
    def parse(text):
        gl = parse(text)
        if len(gl) < 4 or gl[0] != Sym("rule") or gl[-2] != Sym("-->"):
            raise ValueError("expected (rule (fact ...) [conditions] --> (notify ...))")
        f, n = gl[1], gl[-1]
        if not (isinstance(f, tuple) and len(f) == 2 and f[0] == Sym("fact") and isinstance(f[1], tuple)):
            raise ValueError("expected (fact (<Ctx> ...))")
        if not (isinstance(n, tuple) and len(n) == 2 and n[0] == Sym("notify") and isinstance(n[1], tuple)):
            raise ValueError("expected (notify (<Ctx> ...))")
        conds = []
        for c in gl[2:-2]:
            if not (isinstance(c, tuple) and len(c) == 3 and isinstance(c[0], Sym) and c[0].name in OPS
                    and isinstance(c[1], Var)):
                raise ValueError(f"bad condition {fmt(c)}")
            conds.append((c[0].name, c[1].name, c[2].name if isinstance(c[2], Sym) else c[2]))
        if not isinstance(f[1][0], Sym) or len(f[1]) < 2:
            raise ValueError("fact pattern needs a context name and a key")
        return Rule(text, f[1], tuple(conds), n[1])

    @property
    def context(self):
        return self.fact[0].name

    def bind(self, fact):
        """Bindings when the fact matches the pattern and every condition holds, else None."""
        b = unify(self.fact, fact, {})
        if b is None:
            return None
        for op, var, c in self.conds:
            v = b.get(var)
            try:
                if v is None or not OPS[op](v, c):
                    return None
            except TypeError:
                return None
        return b

    def notification(self, b):
        return fmt(subst(self.notify, b))

    def for_instance(self, instance):
        """The unconditional rule of this pattern fixed to one instance (exit watch, A-2-2)."""
        fact = (self.fact[0], instance) + self.fact[2:]
        notify = (self.notify[0], instance) + self.notify[2:] if len(self.notify) >= 2 else self.notify
        return Rule.parse(f"(rule (fact {fmt(fact)}) --> (notify {fmt(notify)}))")


def tombstone_rule(context):
    return Rule.parse(f"(rule (fact (deleted ({context} $key))) --> (notify (deleted ({context} $key))))")


# context vocabulary (public context table) ----------------------------------------------------
_FIELD = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`\s*:")


def field_order(scenario_dir):
    """{context: [value field, ...]} in the order of the public context table (needs.md)."""
    out, on = {}, False
    with open(os.path.join(scenario_dir, "public", "needs.md")) as f:
        for line in f:
            cells = [c.strip() for c in line.strip().strip("|").split("|")] if line.strip().startswith("|") else None
            if cells is None:
                on = False
            elif cells[0] == "컨텍스트":
                on = True
            elif on and not set(cells[0]) <= set("-: "):
                out[cells[0]] = _FIELD.findall(cells[2])
    return out


def gl_value(v):
    if v is None:
        return Sym("nil")
    return int(v) if isinstance(v, bool) else v


def fact_of(order, context, instance, value):
    return (Sym(context), instance) + tuple(gl_value(value.get(f)) for f in order[context])


def tombstone_of(context, instance):
    return (Sym("deleted"), (Sym(context), instance))
