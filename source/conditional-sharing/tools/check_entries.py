"""Consumer-entry check of a role-release scenario (core, in-process) against an independently
written entry table (inputs/expected/contract/CT5-entries.yml).

  python tools/check_entries.py <out.json> [scenario id, default CT5]

Runs the scenario under D, A and A-helper with the core runner classes and, after every step,
reads the consumer entries of the table's agent from the running implementation:
  D        context keys of the agent in the SM's active generated configuration, and the number
           of condition alternatives per context; agent_kept = the agent is still in the active
           configuration's agent (acknowledgement) set
  A, A-h   contexts of the agent's subscriptions held by the LTM; agent_kept = the agent
           acknowledged every change request sent to it
The table is not derived from these readings. Exit status 1 on any mismatch.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "runner"))
import yaml  # noqa: E402
import api  # noqa: E402
import core_run  # noqa: E402
from run_all import exp_path, sc_path  # noqa: E402

ARMS = [("D", {}), ("A", {}), ("A-helper", {"a_variant": "helper"})]


def entries(arm, r, agent):
    if arm == "D":
        per = r.sm.active.gen["consumers"].get(agent, {})
        return sorted(per), {c: len(alts) for c, alts in sorted(per.items())}, agent in r.sm.active.gen["agents"]
    tomb = {sub: c for c, sub in r.agents[agent].tomb.items()}      # tombstone rule -> its context
    ctxs = sorted({tomb.get(sub, rule.context) for sub, (a, rule) in r.ltm.subs.items() if a == agent})
    return ctxs, None, None


def run(sid, arm, variant, table):
    sc = api.load_scenario(sc_path(sid))
    agent = table["agent"]
    r = (core_run.DRun if arm == "D" else core_run.ARun)(sc, variant)
    r.start()
    got, alts, kept, sent = {}, {}, {}, 0
    n = {}
    for step in api.steps(sc):
        if step["kind"] == "report":
            x = (step["context"], step["instance"])
            n[x] = n.get(x, 0) + 1
            r.report(api.envelope(sc, step, n[x], step["i"]))
        elif step["kind"] == "change":
            _, meta = r.change(step["change"], float(step["i"]))
            if arm != "D" and agent in meta.get("targets", []):
                sent += 1
        got[step["id"]], a, k = entries(arm, r, agent)
        if a is not None:
            alts[step["id"]] = a
        kept[step["id"]] = k if arm == "D" else len(r.agents[agent].acks) == sent
    rows = [{"step": s, "what": "entries", "expected": e, "observed": got.get(s), "ok": got.get(s) == e}
            for s, e in table["entries"].items()]
    if arm == "D":
        rows += [{"step": s, "what": "alternatives", "expected": e, "observed": alts.get(s), "ok": alts.get(s) == e}
                 for s, e in (table.get("alternatives") or {}).items()]
    last = list(table["entries"])[-1]
    rows.append({"step": last, "what": "agent_kept", "expected": table["agent_kept"], "observed": kept[last],
                 "ok": kept[last] == table["agent_kept"]})
    return {"scenario": sid, "arm": arm, "agent": agent, "pass": all(x["ok"] for x in rows), "rows": rows}


def main():
    out, sid = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "CT5")
    tpath = exp_path(sid + "-entries")
    with open(tpath) as f:
        table = yaml.safe_load(f)
    res = [run(sid, arm, v, table) for arm, v in ARMS]
    doc = {"table": os.path.relpath(tpath, ROOT), "table_sha256": api.sha256_file(tpath),
           "pass": all(x["pass"] for x in res), "runs": res}
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
    for x in res:
        bad = [r for r in x["rows"] if not r["ok"]]
        print(x["arm"], "PASS" if x["pass"] else "FAIL", len(x["rows"]), "rows", *(json.dumps(b) for b in bad))
    return 0 if doc["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
