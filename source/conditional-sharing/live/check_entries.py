"""Consumer-entry check of one live run from its process logs only (no src/runner/cslive import).

  python3 -I check_entries.py <run_dir> <entries.yml>      (e.g. inputs/expected/contract/CT5-entries.yml)

D  the configuration each change applies is read from the /d/apply messages the SM received; the
   entries of the table's agent at a change step are the context keys of that agent in the applied
   configuration (`alternatives` = condition alternatives per context). Steps before the first
   change are not compared for D (the initial configuration is logged by hash only).
   agent_kept: the agent is in the applied agent set and the SM received its ACK of that seq.
A  the LTM's subscription table is rebuilt from the subscribe / unsubscribe messages it received,
   in receive order; the entries after a step are the contexts of the agent's live subscriptions
   (condition, tombstone and exit-watch rules). agent_kept: the agent acknowledged every load
   request with request_id > 0 it received.
Writes <run_dir>/entries.json; exit status 1 on any mismatch.
"""
import json
import os
import re
import sys

import yaml

CTX = re.compile(r"\(fact \((?:deleted \()?([A-Za-z_]\w*)")


def rows_of(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def check_d(logs, table, order):
    agent, rows = table["agent"], []
    applied, acks = {}, set()
    for r in rows_of(os.path.join(logs, "d-sm.jsonl")):
        if r.get("kind") != "rx":
            continue
        d = json.loads(r["data"])
        if r.get("topic") == "/d/apply":
            applied[r["step"]] = d["gen"]
        elif r.get("topic") == "/d/ack":
            acks.add((d["agent"], d["seq"]))
    seqs = {}
    for r in rows_of(os.path.join(logs, "d-sm.jsonl")):
        if r.get("kind") == "stage":
            seqs[r["step"]] = r["seq"]
    for s in order:
        if s not in applied:
            continue
        per = applied[s]["consumers"].get(agent, {})
        if s in table["entries"]:
            rows.append({"step": s, "what": "entries", "expected": table["entries"][s], "observed": sorted(per)})
        if s in (table.get("alternatives") or {}):
            rows.append({"step": s, "what": "alternatives", "expected": table["alternatives"][s],
                         "observed": {c: len(a) for c, a in sorted(per.items())}})
    last = [s for s in order if s in applied][-1]
    kept = agent in applied[last]["agents"] and (agent, seqs.get(last)) in acks
    rows.append({"step": last, "what": "agent_kept", "expected": table["agent_kept"], "observed": kept})
    return rows


def check_a(logs, table, order):
    agent, rows = table["agent"], []
    subs, at = {}, {}
    for r in sorted((x for x in rows_of(os.path.join(logs, "a-ltm.jsonl"))
                     if x.get("kind") == "rx" and x.get("topic") == "/cs/a/ltm"), key=lambda x: x["seq"]):
        d = json.loads(r["data"])
        if d.get("op") == "subscribe" and d.get("agent") == agent:
            subs[d["sub"]] = CTX.search(d["rule"]).group(1)
        elif d.get("op") == "unsubscribe":
            subs.pop(d["sub"], None)
        at[r["step"]] = sorted(set(subs.values()))
    seen = []
    for s in order:
        if s in at:
            seen = at[s]
        if s in table["entries"]:
            rows.append({"step": s, "what": "entries", "expected": table["entries"][s], "observed": seen})
    loads, acked = set(), set()
    for r in rows_of(os.path.join(logs, f"a-agent-{agent}.jsonl")):
        if r.get("kind") == "rx" and r.get("topic") == f"/cs/a/to/{agent}":
            d = json.loads(r["data"])
            if d.get("type") == "load" and d.get("request_id"):
                loads.add(d["request_id"])
        if r.get("kind") == "tx" and r.get("topic") == "/cs/ready":
            st = (json.loads(r["data"]).get("status") or {}).get(agent) or {}
            acked |= set(st.get("acks") or [])
    last = list(table["entries"])[-1]
    rows.append({"step": last, "what": "agent_kept", "expected": table["agent_kept"],
                 "observed": bool(loads) and loads <= acked})
    return rows


def main():
    run, tpath = sys.argv[1], sys.argv[2]
    with open(tpath) as f:
        table = yaml.safe_load(f)
    with open(os.path.join(run, "plan.json")) as f:
        plan = json.load(f)
    with open(plan["scenario_path"] if os.path.exists(plan["scenario_path"])
              else os.path.join(os.path.dirname(tpath), "..", "..", "scenarios", "contract",
                                os.path.basename(plan["scenario_path"]))) as f:
        sc = yaml.safe_load(f)
    order = ["init"] + [s["id"] for s in sc["steps"]]
    logs = os.path.join(run, "logs")
    rows = (check_d if plan["arm"] == "d" else check_a)(logs, table, order)
    for x in rows:
        x["ok"] = x["expected"] == x["observed"]
    mpath = os.path.join(run, "manifest.json")
    rid = json.load(open(mpath))["run_id"] if os.path.exists(mpath) else os.path.basename(os.path.normpath(run))
    doc = {"run": rid, "arm": plan["arm"], "table": os.path.basename(tpath),
           "pass": bool(rows) and all(x["ok"] for x in rows), "rows": rows}
    with open(os.path.join(run, "entries.json"), "w") as f:
        json.dump(doc, f, indent=1)
    print(doc["run"], "PASS" if doc["pass"] else "FAIL", len(rows), "rows",
          *(json.dumps(x) for x in rows if not x["ok"]))
    return 0 if doc["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
