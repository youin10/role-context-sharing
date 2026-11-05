"""F1 generator: Algorithm 1 with the source-role binding check.

Input: role context specification + binding (one configuration version).
Output (`rcs-d-gen/1`, JSON): the sharing configuration installed into the SM.
  flows      role level: (source role, consumer role, context, condition)  — Algorithm 1
  consumers  agent -> context -> list of AND-condition lists (OR); [[]] = unconditional
  producers  agent -> contexts it reports to the SM (producer report configuration)
  agents     every bound agent (the SM's acknowledgement set)
Generation refuses when the F4 checker reports an error (including the F1 binding check).

  python3 -m arms.d.generator <prepared_scenario_dir>    # every <cfg>/roles.org + binding.yml
"""
from __future__ import annotations

import json
import os
import sys
import time

from arms.d.checker import check, errors
from arms.d.spec import Binding, Spec, load_binding, load_spec_org


class GenerationError(Exception):
    def __init__(self, findings):
        super().__init__("; ".join(f"{f.code} {f.where}: {f.message}" for f in findings))
        self.findings = findings


def generate(spec: Spec, binding: Binding, types=None) -> dict:
    """With `types` (TypeRegistry) the output also carries the argument signatures and the
    fixed individual -> class closure table, so the SM can evaluate class conditions and
    reject reports with unregistered IDs or ill-typed values. Without it the output is the
    original rcs-d-gen/1 document, byte for byte."""
    findings = check(spec, binding, types)
    if errors(findings):
        raise GenerationError(errors(findings))
    bound = {r for rs in binding.agents.values() for r in rs}
    sources = {}
    for r in spec.roles.values():
        for c in r.changes:
            sources.setdefault(c, []).append(r.name)
    # Algorithm 1: for every consumed item of every role, the roles that produce it,
    # restricted to roles that have a bound agent (F1).
    flows = []
    for r in spec.roles.values():
        if r.name not in bound:
            continue
        for rd in r.reads:
            for s in sources.get(rd.context, []):
                if s in bound:
                    flows.append({"source": s, "consumer": r.name, "context": rd.context,
                                  "where": [vars(c) for c in rd.where]})
    consumers = {}
    for a, rs in binding.agents.items():
        per = {}
        for rname in rs:
            for rd in spec.roles[rname].reads:
                alts = per.setdefault(rd.context, [])
                conj = [vars(c) for c in rd.where]
                if conj not in alts:
                    alts.append(conj)
        # an unconditional read subsumes every conditional one
        consumers[a] = {c: ([[]] if [] in alts else alts) for c, alts in sorted(per.items())}
    producers = {a: sorted({c for r in rs for c in spec.roles[r].changes}) for a, rs in binding.agents.items()}
    gen = {
        "schema": "rcs-d-gen/1",
        "cfg": binding.cfg,
        "domain": spec.domain,
        "agents": sorted(binding.agents),
        "keys": {c: v["key"] for c, v in spec.vocabulary.items()},
        "flows": flows,
        "consumers": consumers,
        "producers": producers,
        "sources": {c: {"roles": rs, "agents": sorted(a for a, ars in binding.agents.items() if set(ars) & set(rs))}
                    for c, rs in sorted(sources.items())},
        "warnings": [f.to_dict() for f in findings],
    }
    if types is not None:
        gen["signature"] = {c: {"key": v["key"], "key_type": v["key_type"], "fields": v["fields"]}
                            for c, v in sorted(spec.vocabulary.items())}
        gen["types"] = {"classes": sorted(types.classes),
                        "parents": {c: sorted(ps) for c, ps in sorted(types.parents.items())},
                        "individuals": {i: sorted(cs) for i, cs in sorted(types.individuals.items())},
                        "namespace": types.namespace}
    return gen


def generate_dir(scenario_dir):
    """Generate every configuration version under a prepared scenario directory."""
    out_dir = os.path.join(scenario_dir, "generated")
    os.makedirs(out_dir, exist_ok=True)
    report = {}
    for cfg in sorted(os.listdir(scenario_dir)):
        sp = os.path.join(scenario_dir, cfg, "roles.org")
        if not os.path.isfile(sp):
            continue
        t = time.perf_counter()
        gen = generate(load_spec_org(sp), load_binding(os.path.join(scenario_dir, cfg, "binding.yml")))
        dt = time.perf_counter() - t
        assert gen["cfg"] == cfg, f"binding cfg {gen['cfg']} != directory {cfg}"
        with open(os.path.join(out_dir, f"{cfg}.json"), "w") as f:
            json.dump(gen, f, indent=1, ensure_ascii=False)
        report[cfg] = {"generation_s": round(dt, 6), "flows": len(gen["flows"]),
                       "consumer_entries": sum(len(v) for v in gen["consumers"].values())}
    with open(os.path.join(out_dir, "generation-report.json"), "w") as f:
        json.dump(report, f, indent=1)
    return report


if __name__ == "__main__":
    for d in sys.argv[1:]:
        print(d, json.dumps(generate_dir(d)))
