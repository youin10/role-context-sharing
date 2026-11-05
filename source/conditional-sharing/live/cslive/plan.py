"""Process plan of one live run, from the scenario input and runner/api.py only.

Observed agents get one process each; every other agent (producers included) shares the
`<arm>-producer` process. A hosts exactly the agents of the initial A file (as the core runner
does); D hosts every agent bound in the initial or a changed binding.
"""
from __future__ import annotations

import json
import os
import sys

import yaml

import api


def agents_d(sc):
    out = set()
    for d in [sc["d"]] + [s["change"]["d"] for s in sc["steps"] if "change" in s]:
        with open(os.path.join(api.INPUTS, "models", "d", d["binding"] + ".yml")) as f:
            out |= set((yaml.safe_load(f) or {}).get("agents", {}))
    return sorted(out)


def agents_a(sc, a_variant=None):
    doc, _ = api.a_initial(sc, None, api.a_dir(a_variant))
    return sorted(doc["agents"])


def producers(sc):
    return sorted({s[k][0] for s in sc["steps"] for k in ("report", "delete") if k in s})


def plan(sc, arm, a_variant=None):
    observed = list(sc.get("observe", []))
    if arm == "d":
        agents = sorted(set(agents_d(sc)) | set(producers(sc)))
    else:
        agents = agents_a(sc, a_variant)
        missing = sorted(set(producers(sc)) - set(agents))
        if missing:     # the core runner fails the same way (no A agent to emit through)
            raise ValueError(f"A producers without an A agent: {missing}")
    rest = sorted(set(agents) - set(observed))
    procs = {"driver": [], f"{arm}-producer": rest, ("d-sm" if arm == "d" else "a-ltm"): []}
    for a in observed:
        procs[f"{arm}-agent-{a}"] = [a]
    return {"arm": arm, "a_variant": a_variant, "scenario": sc["id"], "scenario_path": sc["_path"],
            "observed": observed, "agents": agents, "producers": producers(sc), "procs": procs}


if __name__ == "__main__":
    # python3 -m cslive.plan <scenario.yml> <arm> <out plan.json> [a_variant]
    _, scenario_path, arm, out = sys.argv[:4]
    av = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] != "-" else None
    with open(out, "w") as f:
        json.dump(plan(api.load_scenario(scenario_path), arm, av), f, indent=1)
