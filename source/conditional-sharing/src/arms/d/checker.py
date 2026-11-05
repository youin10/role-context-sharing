"""F4 input checker: detect defects of the role context specification and binding before
deployment (R4-M10, R5-5). Four categories, as in the reviewer comment:

  incomplete  INCOMPLETE_BINDING  a consumed context whose only source roles have no bound
                                  agent (F1 binding check); an agent with an empty role list
                                  is a valid assignment (no reads, no changes)
  conflict    DUPLICATE_READ      a role declares the same context twice
              UNSATISFIABLE       an AND condition no value can satisfy
  sourceless  SOURCELESS          a consumed context that no role declares in `changes`
  identifier  UNKNOWN_CONTEXT / UNKNOWN_FIELD / UNKNOWN_ROLE / TYPE_MISMATCH / BAD_ID /
              BAD_VOCABULARY

Every finding is an error (deployment is refused) except UNUSED_ROLE (warning).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from arms.d.spec import Binding, Spec
from arms.d.ontology import XSD

ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
CATEGORY = {
    "INCOMPLETE_BINDING": "incomplete", "DUPLICATE_READ": "conflict", "UNSATISFIABLE": "conflict",
    "SOURCELESS": "sourceless", "UNKNOWN_CONTEXT": "identifier", "UNKNOWN_FIELD": "identifier",
    "UNKNOWN_ROLE": "identifier", "TYPE_MISMATCH": "identifier", "BAD_ID": "identifier",
    "BAD_VOCABULARY": "identifier", "UNUSED_ROLE": "incomplete",
    "UNKNOWN_CLASS": "identifier", "UNKNOWN_INDIVIDUAL": "identifier",
}


@dataclass(frozen=True)
class Finding:
    code: str
    where: str
    message: str

    @property
    def category(self):
        return CATEGORY[self.code]

    @property
    def severity(self):
        return "warning" if self.code == "UNUSED_ROLE" else "error"

    def to_dict(self):
        return {"code": self.code, "category": self.category, "severity": self.severity,
                "where": self.where, "message": self.message}


def _ftype_ok(ftype):
    return (isinstance(ftype, str) and ":" in ftype) or ftype in ("int", "str", "bool") or (isinstance(ftype, dict) and isinstance(ftype.get("enum"), list))


def _entity_error(ftype, c, types):
    """Condition on an entity-valued argument (argumentType is an ontology class)."""
    if types is None:
        return "UNKNOWN_CLASS", f"{c.field} is entity-valued ({ftype}) but no type registry is loaded"
    if ftype not in types.classes:
        return "UNKNOWN_CLASS", f"argumentType {ftype} of {c.field} is not a declared class"
    if c.op in ("isa", "!isa"):
        if c.value not in types.classes:
            return "UNKNOWN_CLASS", f"unknown class {c.value} in condition on {c.field}"
        if not types.compatible(c.value, ftype):
            return "TYPE_MISMATCH", (f"no declared subclass and no registered individual is both {c.value} and "
                                     f"argumentType {ftype} of {c.field} (fixed catalogue)")
        return None
    if c.op in ("<", "<=", ">", ">="):
        return "TYPE_MISMATCH", f"ordered operator {c.op} on identifier field {c.field}"
    if not isinstance(c.value, str):
        return "TYPE_MISMATCH", f"{c.field} holds individual IDs of {ftype} but constant {c.value!r} is not an ID"
    if c.value not in types.individuals:
        return "UNKNOWN_INDIVIDUAL", f"individual {c.value!r} is not registered (a class needs a prefixed name)"
    if ftype not in types.types_of(c.value):
        return "TYPE_MISMATCH", f"individual {c.value!r} is not a {ftype}"
    return None


def _is_entity(ftype):
    return isinstance(ftype, str) and ":" in ftype and not ftype.startswith(XSD)


def _type_error(ftype, c):
    if c.op in ("isa", "!isa"):
        return f"class condition on literal field {c.field} ({ftype})"
    if isinstance(ftype, str) and ":" in ftype:
        numeric = ftype in (XSD + "integer", XSD + "decimal", XSD + "float", XSD + "double")
        if c.op in ("<", "<=", ">", ">=") and not numeric:
            return f"ordered operator {c.op} on non-numeric field {c.field}"
        valid = ((type(c.value) in (int, float)) if numeric else
                 isinstance(c.value, str) if ftype == XSD + "string" else
                 type(c.value) is bool if ftype == XSD + "boolean" else False)
        if not valid:
            return f"{c.field} has argumentType {ftype} but constant {c.value!r} does not match"
        return None
    if ftype == "str" and not isinstance(c.value, str):
        return f"{c.field} is str but constant {c.value!r} is not"
    if c.op in ("<", "<=", ">", ">=") and ftype != "int":
        return f"ordered operator {c.op} on non-int field {c.field}"
    if ftype == "int" and not (isinstance(c.value, int) and not isinstance(c.value, bool)):
        return f"{c.field} is int but constant {c.value!r} is not"
    if ftype == "bool" and not isinstance(c.value, bool):
        return f"{c.field} is bool but constant {c.value!r} is not"
    if isinstance(ftype, dict) and c.value not in ftype["enum"]:
        return f"{c.value!r} is not in enum {ftype['enum']} of {c.field}"
    return None


def _unsatisfiable(conds, fields=None):
    import math
    by_field = {}
    for c in conds:
        by_field.setdefault(c.field, []).append(c)
    for f, cs in by_field.items():
        eq = {c.value for c in cs if c.op == "="}
        ne = {c.value for c in cs if c.op == "!="}
        if len(eq) > 1 or eq & ne:
            return f
        lo, hi = float("-inf"), float("inf")
        lo_open = hi_open = False
        for c in cs:
            if type(c.value) not in (int, float):
                continue
            if c.op in (">", ">="):
                if c.value > lo:
                    lo, lo_open = c.value, c.op == ">"
                elif c.value == lo:
                    lo_open |= c.op == ">"
            if c.op in ("<", "<="):
                if c.value < hi:
                    hi, hi_open = c.value, c.op == "<"
                elif c.value == hi:
                    hi_open |= c.op == "<"
        if (fields or {}).get(f) in ("int", XSD + "integer"):
            lo = (math.floor(lo) + 1 if lo_open else math.ceil(lo)) if math.isfinite(lo) else lo
            hi = (math.ceil(hi) - 1 if hi_open else math.floor(hi)) if math.isfinite(hi) else hi
            lo_open = hi_open = False
        if lo > hi or (lo == hi and (lo_open or hi_open)):
            return f
        for v in eq:
            if type(v) in (int, float) and (not lo <= v <= hi or
                    (v == lo and lo_open) or (v == hi and hi_open)):
                return f
    return None


def check(spec: Spec, binding: Binding | None = None, types=None) -> list[Finding]:
    out = []
    voc = spec.vocabulary
    for cname, body in voc.items():
        if not ID_RE.match(cname) or not isinstance(body, dict) or "key" not in body \
                or not all(_ftype_ok(t) for t in (body.get("fields") or {}).values()):
            out.append(Finding("BAD_VOCABULARY", f"vocabulary.{cname}", "needs an identifier name, `key` and typed fields"))
    producers = {}
    for r in spec.roles.values():
        for c in r.changes:
            if c not in voc:
                out.append(Finding("UNKNOWN_CONTEXT", f"roles.{r.name}.changes", f"unknown context {c}"))
            producers.setdefault(c, []).append(r.name)
    for r in spec.roles.values():
        if not ID_RE.match(r.name):
            out.append(Finding("BAD_ID", f"roles.{r.name}", "role name is not an identifier"))
        seen = {}
        for rd in r.reads:
            where = f"roles.{r.name}.reads.{rd.context}"
            if rd.context in seen and (rd.alternative_group is None or seen[rd.context] != rd.alternative_group):
                out.append(Finding("DUPLICATE_READ", where, f"{r.name} declares {rd.context} more than once"))
            seen[rd.context] = rd.alternative_group
            if rd.context not in voc:
                out.append(Finding("UNKNOWN_CONTEXT", where, f"unknown context {rd.context}"))
                continue
            fields = dict(voc[rd.context].get("fields") or {})
            if "key_type" in voc[rd.context]:
                fields[voc[rd.context]["key"]] = voc[rd.context]["key_type"]
            for c in rd.where:
                if c.field not in fields:
                    out.append(Finding("UNKNOWN_FIELD", where, f"{rd.context} has no field {c.field}"))
                    continue
                if types is not None and _is_entity(fields[c.field]):
                    err = _entity_error(fields[c.field], c, types)
                    if err:
                        out.append(Finding(err[0], where, err[1]))
                    continue
                err = _type_error(fields[c.field], c)
                if err:
                    out.append(Finding("TYPE_MISMATCH", where, err))
            f = _unsatisfiable(rd.where, fields)
            group = [x for x in r.reads if x.alternative_group == rd.alternative_group] if rd.alternative_group is not None else [rd]
            if f and rd is group[0] and all(_unsatisfiable(x.where, fields) for x in group):
                out.append(Finding("UNSATISFIABLE", where, f"conditions on {f} exclude every value"))
            if rd.context not in producers:
                out.append(Finding("SOURCELESS", where, f"no role declares {rd.context} in changes"))
    for r in spec.roles.values():
        for pattern in r.change_patterns:
            body = voc[pattern.context]
            fields = dict(body["fields"], **{body["key"]: body["key_type"]})
            for c in pattern.where:
                err = _type_error(fields[c.field], c)
                if err:
                    out.append(Finding("TYPE_MISMATCH", f"roles.{r.name}.changes.{pattern.context}", err))
    if binding is None:
        return out
    bound_roles = set()
    for a, rs in binding.agents.items():
        if not ID_RE.match(str(a)):
            out.append(Finding("BAD_ID", f"binding.{a}", "agent id must be an identifier (used in topic names)"))
        for r in rs:
            if r not in spec.roles:
                out.append(Finding("UNKNOWN_ROLE", f"binding.{a}", f"unknown role {r}"))
            else:
                bound_roles.add(r)
    # F1: a bound consumer needs a bound source role, not only a declared one
    for r in sorted(bound_roles):
        for rd in spec.roles[r].reads:
            srcs = producers.get(rd.context, [])
            if srcs and not any(s in bound_roles for s in srcs):
                out.append(Finding("INCOMPLETE_BINDING", f"roles.{r}.reads.{rd.context}",
                                   f"source roles {srcs} of {rd.context} have no bound agent"))
    for r in spec.roles:
        if r not in bound_roles:
            out.append(Finding("UNUSED_ROLE", f"roles.{r}", f"role {r} has no bound agent"))
    return out


def errors(findings):
    return [f for f in findings if f.severity == "error"]
