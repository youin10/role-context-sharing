"""Baseline A helpers that use the shared known entity catalogue (predicate signatures + fixed
individual types). Added for the conditional-sharing experiment; NOT part of the reimplemented
ARBI-style A (arms/a/core.py) and counted separately as baseline helper code.

  check_plans(plans_dir, signature, types)  static check of hand-written GL rules before
                                            deployment: context, arity, bound condition
                                            variables, individual IDs registered and of the
                                            argument's class, literal constant types, no
                                            ordered comparison on IDs or strings
  GuardedLTM                                LTM that refuses writes the catalogue rejects
                                            (same arms.d.ontology.report_error as the D SM)
"""
from __future__ import annotations

import os

import yaml

from arms.a import gl
from arms.a.core import LTMCore
from arms.d.ontology import XSD, report_error

ORDERED = ("<", "<=", ">", ">=")


def _const_error(atype, op, c, types):
    if atype.startswith(XSD):
        numeric = atype in (XSD + "integer", XSD + "decimal", XSD + "float", XSD + "double")
        if op in ORDERED and not numeric:
            return "TYPE_MISMATCH", f"ordered {op} on non-numeric {atype}"
        ok = (type(c) is int if atype == XSD + "integer" else type(c) in (int, float) if numeric
              else isinstance(c, str) if atype == XSD + "string" else c in (0, 1))
        return None if ok else ("TYPE_MISMATCH", f"{c!r} is not a {atype}")
    if op in ORDERED:
        return "TYPE_MISMATCH", f"ordered {op} on identifier of {atype}"
    if not isinstance(c, str):
        return "TYPE_MISMATCH", f"{c!r} is not an individual ID"
    if c not in types.individuals:
        return "UNKNOWN_INDIVIDUAL", f"{c!r} is not registered"
    if atype not in types.types_of(c):
        return "TYPE_MISMATCH", f"{c!r} is not a {atype}"
    return None


def check_rule(text, signature, types):
    try:
        rule = gl.Rule.parse(text)
    except (ValueError, TypeError) as e:
        return [("PARSE_ERROR", str(e))]
    s = signature.get(rule.context)
    if s is None:
        return [("UNKNOWN_CONTEXT", rule.context)]
    types_by_pos = [s["key_type"], *s["fields"].values()]
    if len(rule.fact) != 1 + len(types_by_pos):
        return [("ARITY", f"{rule.context} needs {len(types_by_pos)} arguments")]
    out = []
    pos = {}
    for i, e in enumerate(rule.fact[1:]):
        if isinstance(e, gl.Var):
            pos[e.name] = i
        else:
            err = _const_error(types_by_pos[i], "=", e, types)
            if err:
                out.append(err)
    for op, var, c in rule.conds:
        if var not in pos:
            out.append(("UNBOUND_VARIABLE", var))
            continue
        err = _const_error(types_by_pos[pos[var]], op, c, types)
        if err:
            out.append(err)
    return out


def check_plans(plans_dir, signature, types):
    """[(file, rule index, code, message)] for every plan file of a plan revision directory."""
    out = []
    for name in sorted(os.listdir(plans_dir)):
        if not name.endswith(".yml"):
            continue
        with open(os.path.join(plans_dir, name)) as f:
            doc = yaml.safe_load(f) or {}
        for i, text in enumerate(doc.get("subscribe") or []):
            for code, msg in check_rule(text, signature, types):
                out.append((name, i, code, msg))
    return out


class GuardedLTM(LTMCore):
    def __init__(self, bus, signature, types):
        super().__init__(bus)
        self.signature, self.types = signature, types
        self.rejected = []

    def receive(self, d):
        if d["op"] in ("assert", "update") and d.get("env") is not None:
            env = d["env"]
            err = report_error(self.signature, self.types, env["context"], env["instance"], env["op"], env["value"])
            if err:
                self.rejected.append({"event_id": env["event_id"], "code": err[0], "message": err[1]})
                return
        super().receive(d)
