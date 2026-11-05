"""Stronger baseline A helpers (sensitivity analysis; counted as one-time A helper code).

Inputs are A-owned files plus the shared static ontology (predicate signatures and fixed
individual types, via arms.d.ontology loaders). The D EBNF parser, checker and generator are
NOT used.

  expand_role(entries, signature, types)  per-type threshold entries -> per-ID GL rule texts
  write_plans(config, out_dir, ...)       one <Role>.yml per role of an A config revision
  targets(assign_from, assign_to, dir_from, dir_to)
                                          role-based deployment target list: every agent whose
                                          role list changed or one of whose roles' plan files differ

Config entry forms (one list per role):
  {context: C}                                            unconditional rule
  {context: C, conds: [[op, field, const], ...]}          conditions on value fields
  {context: C, field: f, class: K, conds: [...]}          one rule per registered individual that
                                                          is a K and valid for argument f
  {context: C, field: f, not_class: K, conds: [...]}      ... valid for f and not a K
  {context: C, field: f, ids: [i, ...], conds: [...]}     listed individual IDs
"""
from __future__ import annotations

import json
import os

import yaml

NS_DEFAULT = "http://ai.uos.ac.kr/logistics-ontology#"


def _const(c):
    return json.dumps(c) if isinstance(c, str) else str(c)


def _rule(context, args, conds):
    pattern = f"({context} " + " ".join("$" + a for a in args) + ")"
    cs = "".join(f" ({op} ${f} {_const(v)})" for op, f, v in conds)
    return f"(rule (fact {pattern}){cs} --> (notify {pattern}))"


def _arg_type(sig, field):
    return sig["key_type"] if field == sig["key"] else sig["fields"][field]


def expand_role(entries, signature, types, ns=NS_DEFAULT):
    rules = []
    for e in entries:
        sig = signature[e["context"]]
        args = [sig["key"], *sig["fields"]]
        conds = [list(c) for c in e.get("conds", [])]
        if not any(k in e for k in ("class", "not_class", "ids")):
            rules.append(_rule(e["context"], args, conds))
            continue
        f = e["field"]
        atype = _arg_type(sig, f)
        valid = sorted(i for i in types.individuals if atype in types.types_of(i))
        if "class" in e:
            ids = [i for i in valid if ns + e["class"] in types.types_of(i)]
        elif "not_class" in e:
            ids = [i for i in valid if ns + e["not_class"] not in types.types_of(i)]
        else:
            missing = [i for i in e["ids"] if i not in valid]
            if missing:
                raise ValueError(f"{e['context']}.{f}: {missing} are not registered {atype} individuals")
            ids = list(e["ids"])
        for i in ids:
            rules.append(_rule(e["context"], args, [["=", f, i]] + conds))
    return rules


def write_plans(config, out_dir, signature, types, header=""):
    os.makedirs(out_dir, exist_ok=True)
    for role, entries in sorted(config["roles"].items()):
        rules = expand_role(entries or [], signature, types)
        with open(os.path.join(out_dir, f"{role}.yml"), "w") as f:
            f.write(header)
            yaml.safe_dump({"role": role, "subscribe": rules}, f, sort_keys=False, width=1000)


def _plan_text(d, role):
    p = os.path.join(d, f"{role}.yml")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return (yaml.safe_load(f) or {}).get("subscribe")


def targets(assign_from, assign_to, dir_from, dir_to):
    out = {}
    for a in sorted(set(assign_from) | set(assign_to)):
        before, after = list(assign_from.get(a, [])), list(assign_to.get(a, []))
        if a not in assign_to:
            continue
        if before != after or any(_plan_text(dir_from, r) != _plan_text(dir_to, r) for r in after):
            out[a] = {"roles": after}
    return out
