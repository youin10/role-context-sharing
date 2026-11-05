"""Negative controls for the judge itself: mutate a passing raw log (or the scenario / expected
inputs) and check the judge CLI exits 1; the unmutated input and a mutation of raw start.observe
(which the judge must not depend on) exit 0.

  python tools/judge_mutation_nc.py <run_dir>      (uses <run_dir>/raw/main/B1__D__main.jsonl, P1__D__main.jsonl)
"""
import copy, json, os, subprocess, sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
run_dir = sys.argv[1]
out_dir = os.path.join(run_dir, "judge-nc")
os.makedirs(out_dir, exist_ok=True)


def load(p):
    return [json.loads(l) for l in open(p) if l.strip()]


def step(rows, sid):
    return next(r for r in rows if r.get("rec") == "step" and r["step"] == sid)


def m_drop(rows, sid):
    return [r for r in rows if not (r.get("rec") == "step" and r["step"] == sid)]


def m_dup(rows, sid):
    i = next(k for k, r in enumerate(rows) if r.get("step") == sid)
    return rows[:i + 1] + [copy.deepcopy(rows[i])] + rows[i + 1:]


def m_swap(rows, a, b):
    ia = next(k for k, r in enumerate(rows) if r.get("step") == a)
    ib = next(k for k, r in enumerate(rows) if r.get("step") == b)
    rows = list(rows)
    rows[ia], rows[ib] = rows[ib], rows[ia]
    return rows


def edit(rows, fn):
    rows = copy.deepcopy(rows)
    fn(rows)
    return rows


B1 = load(os.path.join(run_dir, "raw/main/B1__D__main.jsonl"))
P1 = load(os.path.join(run_dir, "raw/main/P1__D__main.jsonl"))
E = {k: os.path.join(ROOT, f"inputs/expected/{k}.yml") for k in ("B1", "P1")}
S = {k: os.path.join(ROOT, f"inputs/scenarios/{k}.yml") for k in ("B1", "P1")}
sc_b1 = yaml.safe_load(open(S["B1"]))
ex_b1 = yaml.safe_load(open(E["B1"]))

CASES = [  # (id, description, raw rows, expected path or dict, scenario path or dict, want exit)
    ("J00", "unmutated B1", B1, E["B1"], S["B1"], 0),
    ("J00b", "unmutated P1", P1, E["P1"], S["P1"], 0),
    ("J01", "step s05 deleted", m_drop(B1, "s05"), E["B1"], S["B1"], 1),
    ("J02", "step s05 duplicated", m_dup(B1, "s05"), E["B1"], S["B1"], 1),
    ("J03", "steps s02/s03 reordered", m_swap(B1, "s02", "s03"), E["B1"], S["B1"], 1),
    ("J04", "unexpected step inserted", B1[:3] + [dict(copy.deepcopy(B1[2]), step="zz")] + B1[3:], E["B1"], S["B1"], 1),
    ("J05", "start record removed", B1[1:], E["B1"], S["B1"], 1),
    ("J06", "end record removed", B1[:-1], E["B1"], S["B1"], 1),
    ("J07", "end carries an error", edit(B1, lambda r: r[-1].update(error="boom")), E["B1"], S["B1"], 1),
    ("J08", "observer manager1 missing from views at s01 (no expected view there)",
     edit(B1, lambda r: step(r, "s01")["views"].pop("manager1")), E["B1"], S["B1"], 1),
    ("J09", "empty roster in the scenario", B1, E["B1"], dict(sc_b1, observe=[]), 1),
    ("J10", "first positive call removed (s02)", edit(B1, lambda r: step(r, "s02")["calls"].pop("manager1")), E["B1"], S["B1"], 1),
    ("J11", "call value changed (s03 battery 28)",
     edit(B1, lambda r: step(r, "s03")["calls"]["manager1"][0][3].update(battery=28)), E["B1"], S["B1"], 1),
    ("J12", "duplicate assert at s02",
     edit(B1, lambda r: step(r, "s02")["calls"]["manager1"].append(step(r, "s02")["calls"]["manager1"][0])), E["B1"], S["B1"], 1),
    ("J13", "raw start.observe emptied (judge must not depend on it)",
     edit(B1, lambda r: r[0].update(observe=[])), E["B1"], S["B1"], 0),
    ("J14", "decision changed at P1 D3", edit(P1, lambda r: step(r, "D3")["decision"].update(wheeled1=[])), E["P1"], S["P1"], 1),
    ("J15", "decision missing at P1 D4", edit(P1, lambda r: step(r, "D4").pop("decision")), E["P1"], S["P1"], 1),
    ("J16", "unexpected rejection at s01", edit(B1, lambda r: step(r, "s01").update(rejected=[{"code": "TYPE_MISMATCH"}])), E["B1"], S["B1"], 1),
    ("J17", "expected names a step not in the scenario", B1, dict(ex_b1, calls=dict(ex_b1["calls"], s99={})), S["B1"], 1),
    ("J18", "expected names an agent outside the roster", B1,
     dict(ex_b1, calls=dict(ex_b1["calls"], s01={"tech1": []})), S["B1"], 1),
    ("J20", "update reported as assert (s03)",
     edit(B1, lambda r: step(r, "s03")["calls"]["manager1"][0].__setitem__(0, "assert")), E["B1"], S["B1"], 1),
    ("J21", "retract reported as a second assert (first retract of B1)",
     edit(B1, lambda r: next(c for x in r if x.get("rec") == "step" for c in (x.get("calls") or {}).get("manager1", [])
                             if c[0] == "retract").__setitem__(0, "assert")), E["B1"], S["B1"], 1),
    ("J19", "all calls removed (empty observation)", edit(B1, lambda r: [x.update(calls={}) for x in r if x.get("rec") == "step"]), E["B1"], S["B1"], 1),
]

res = []
for cid, desc, rows, exp, sc, want in CASES:
    d = os.path.join(out_dir, cid)
    os.makedirs(d, exist_ok=True)
    rp = os.path.join(d, "raw.jsonl")
    with open(rp, "w") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    paths = []
    for name, obj in (("expected.yml", exp), ("scenario.yml", sc)):
        if isinstance(obj, dict):
            p = os.path.join(d, name)
            yaml.safe_dump(obj, open(p, "w"), sort_keys=False)
            paths.append(p)
        else:
            paths.append(obj)
    pr = subprocess.run([sys.executable, os.path.join(ROOT, "runner/judge.py"), rp, *paths], capture_output=True, text=True)
    open(os.path.join(d, "judge.stdout.txt"), "w").write(pr.stdout + pr.stderr)
    res.append({"id": cid, "mutation": desc, "want_exit": want, "exit": pr.returncode, "ok": pr.returncode == want,
                "last_line": pr.stdout.strip().splitlines()[-1] if pr.stdout.strip() else pr.stderr[-200:]})
json.dump(res, open(os.path.join(run_dir, "judge_nc.json"), "w"), indent=1)
for r in res:
    print("ok " if r["ok"] else "BAD", r["id"], r["exit"], r["mutation"], "|", r["last_line"])
sys.exit(0 if all(r["ok"] for r in res) else 1)
