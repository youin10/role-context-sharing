"""Raw negative controls for the live judge: mutate a copy of one run's raw logs and require
the judge to FAIL every mutation (the unmutated copy must reproduce the original verdict).

  python3 -I nc_raw.py <run_dir> <d|a> <scenario.yml> <expected.yml> <out.json>
Mutations (applied to a temporary copy; the run directory is never changed):
  drop-observer    delete the first observed agent's log
  empty-observer   truncate it to zero bytes
  drop-step        remove every record of one step that has expected calls, from every log
  dup-call         duplicate one call record
  dup-rx           duplicate one inbox receipt
  swap-steps       swap the driver's first two settled records (order change)
  no-end           remove the end control message and every final/exit record
  drop-rx          remove the inbox receipt that caused one call (message loss)
  value            change the value of one call
  kind             change the notification kind of one call (assert <-> update, retract -> assert)
"""
import copy
import json
import os
import shutil
import sys
import tempfile

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import judge  # noqa: E402  (live/judge.py; standard library + yaml only)


def load(d):
    out = {}
    for fn in sorted(os.listdir(os.path.join(d, "logs"))):
        if fn.endswith(".jsonl"):
            with open(os.path.join(d, "logs", fn)) as f:
                out[fn[:-6]] = [json.loads(x) for x in f if x.strip()]
    return out


def save(d, logs):
    for p, rows in logs.items():
        with open(os.path.join(d, "logs", p + ".jsonl"), "w") as f:
            for r in rows:
                f.write(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n")


def first(logs, proc, pred):
    return next((k for k, r in enumerate(logs.get(proc, [])) if pred(r)), None)


def mutate(name, logs, sc, exp, arm):
    obs = f"{arm}-agent-{sc['observe'][0]}"
    pos = [s for s, per in (exp.get("calls") or {}).items() if any(per.values())] if exp.get("calls") else []
    call_proc = next((p for p, rs in logs.items() if any(r.get("kind") == "call" for r in rs)), None)
    if name == "drop-observer":
        logs.pop(obs, None)
        return "removed"
    if name == "empty-observer":
        logs[obs] = []
        return "emptied"
    if name == "drop-step":
        sid = pos[0] if pos else sc["steps"][0]["id"]
        for p in logs:
            logs[p] = [r for r in logs[p] if r.get("step") != sid]
        return sid
    if name == "swap-steps":
        idx = [k for k, r in enumerate(logs["driver"]) if r.get("kind") == "settled"][:2]
        d = logs["driver"]
        d[idx[0]], d[idx[1]] = d[idx[1]], d[idx[0]]
        return idx
    if name == "no-end":
        for p in logs:
            logs[p] = [r for r in logs[p] if r.get("kind") not in ("final", "exit")
                       and not (r.get("topic") == "/cs/ctl" and '"phase":"end"' in r.get("data", ""))]
        return "removed"
    if call_proc is None:
        return None                                   # no call to mutate (zero-positive table)
    k = first(logs, call_proc, lambda r: r.get("kind") == "call")
    r = logs[call_proc][k]
    if name == "dup-call":
        logs[call_proc].insert(k + 1, copy.deepcopy(r))
    elif name == "dup-rx":
        j = r["cause"]["rx_seq"]
        rx = next(x for x in logs[call_proc] if x.get("seq") == j)
        logs[call_proc].insert(logs[call_proc].index(rx) + 1, copy.deepcopy(rx))
    elif name == "drop-rx":
        j = r["cause"]["rx_seq"]
        logs[call_proc] = [x for x in logs[call_proc] if x.get("seq") != j]
    elif name == "value":
        r["v"] = {"mutated": True}
    elif name == "kind":
        r["call"] = {"assert": "update", "update": "assert"}.get(r["call"], "assert")
    return [call_proc, r.get("step")]


NAMES = ["drop-observer", "empty-observer", "drop-step", "dup-call", "dup-rx", "swap-steps", "no-end", "drop-rx",
         "value", "kind"]


def main():
    run_dir, arm, sc_path, exp_path, out = sys.argv[1:6]
    with open(sc_path) as f:
        sc = yaml.safe_load(f)
    with open(exp_path) as f:
        exp = yaml.safe_load(f)
    base = judge.judge(run_dir, sc, exp, arm)["verdict"]
    res = {"original": base, "mutations": []}
    for name in ["identity"] + NAMES:
        tmp = tempfile.mkdtemp(prefix="cslive-nc-")
        try:
            shutil.copytree(run_dir, os.path.join(tmp, "r"), ignore=shutil.ignore_patterns("nc*", "judge*"))
            d = os.path.join(tmp, "r")
            logs = load(d)
            what = "none" if name == "identity" else mutate(name, logs, sc, exp, arm)
            if what is None:
                res["mutations"].append({"name": name, "applicable": False})
                continue
            shutil.rmtree(os.path.join(d, "logs"))
            os.makedirs(os.path.join(d, "logs"))
            save(d, logs)
            v = judge.judge(d, sc, exp, arm)
            res["mutations"].append({"name": name, "applicable": True, "where": what, "verdict": v["verdict"],
                                     "problems": sorted({p["what"] for p in v["problems"]}),
                                     "mismatches": len(v["mismatches"])})
        finally:
            shutil.rmtree(tmp)
    applied = [m for m in res["mutations"] if m["applicable"] and m["name"] != "identity"]
    ident = res["mutations"][0]
    res["ok"] = ident["verdict"] == base and all(m["verdict"] == "FAIL" for m in applied)
    res["detected"] = sum(m["verdict"] == "FAIL" for m in applied)
    res["applied"] = len(applied)
    with open(out, "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps({"original": base, "ok": res["ok"], "detected": res["detected"], "applied": res["applied"]}))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
