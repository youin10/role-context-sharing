"""Judge: compares a raw run log with an expected table written independently of the implementation and the scenario file.

Independence: imports only the standard library and PyYAML; never the implementation under
test (arms.*, rcs.*), the runner, or generated configurations. Exit status 1 on any failure.

  python runner/judge.py <raw.jsonl> <expected.yml> <scenario.yml>

The observer roster and the step order come from the scenario file, never from the raw log:
  - exactly one `start` record first and one `end` record last, end without error, the start
    names the scenario;
  - step records are exactly the scenario's step ids in order (no missing, duplicated, reordered
    or unexpected step);
  - every roster agent has a view entry at every step (missing observer = FAIL); an empty roster,
    or an expected agent / step outside the roster / scenario, is a FAIL;
  - calls of every roster agent at every non-decision step equal the expected list exactly
    (no expected entry = no calls); decision steps carry a decision when one is expected;
  - the number of expected positive calls actually compared must equal the number in the table
    and be > 0 unless the table declares `no_positive_calls: true` (removal control).
"""
from __future__ import annotations

import json
import sys

import yaml


def load_raw(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def _calls(cs):
    return [[c[0], c[1], c[2], c[3]] for c in cs]


def judge(raw, expected, scenario):
    rows = []

    def row(step, what, exp, got):
        rows.append({"step": step, "what": what, "expected": exp, "observed": got, "ok": exp == got})

    roster = list(scenario.get("observe") or [])
    order = [s["id"] for s in scenario["steps"]]
    decide_ids = {s["id"] for s in scenario["steps"] if s.get("decide")}
    row("-", "roster-nonempty", True, bool(roster))
    # framing
    recs = [r.get("rec") for r in raw]
    row("-", "first-record-is-start", "start", recs[0] if recs else None)
    row("-", "last-record-is-end", "end", recs[-1] if recs else None)
    row("-", "start-count", 1, recs.count("start"))
    row("-", "end-count", 1, recs.count("end"))
    row("-", "error-records", 0, recs.count("error"))
    start = next((r for r in raw if r.get("rec") == "start"), {})
    end = next((r for r in raw if r.get("rec") == "end"), {})
    row("-", "start-scenario", scenario["id"], start.get("scenario"))
    row("-", "end-error", None, end.get("error", "missing end"))
    steps = [r for r in raw if r.get("rec") == "step"]
    row("-", "step-order", order, [s.get("step") for s in steps])
    by_id = {}
    for s in steps:
        by_id.setdefault(s.get("step"), s)
    # expected table refers only to scenario steps and roster agents
    exp_calls = expected.get("calls") or {}
    for section in ("calls", "views", "decisions", "store", "rejected"):
        for sid in (expected.get(section) or {}):
            if sid not in order:
                row(sid, f"expected-{section}-step-in-scenario", True, False)
    for sid, agents in list(exp_calls.items()) + list((expected.get("views") or {}).items()):
        for a in (agents or {}):
            if a not in roster:
                row(sid, f"expected-agent-{a}-in-roster", True, False)
    compared_positive = 0
    for sid in order:
        s = by_id.get(sid)
        if s is None:
            continue
        views = s.get("views") or {}
        for a in roster:
            if a not in views:
                row(sid, f"view-present:{a}", True, False)
        if sid in decide_ids:
            continue
        want = exp_calls.get(sid) or {}
        for a in roster:
            exp = _calls((want or {}).get(a, []))
            got = _calls((s.get("calls") or {}).get(a, []))
            compared_positive += len(exp)
            row(sid, f"calls:{a}", exp, got)
        got_rej = sorted(x["code"] for x in s.get("rejected", []))
        row(sid, "rejected", sorted(((expected.get("rejected") or {}).get(sid, []))), got_rej)
    for sid, agents in (expected.get("views") or {}).items():
        s = by_id.get(sid)
        for a, exp in agents.items():
            row(sid, f"view:{a}", exp, None if s is None else (s.get("views") or {}).get(a))
    for sid, items in (expected.get("store") or {}).items():
        s = by_id.get(sid)
        for item, exp in items.items():
            row(sid, f"store:{item}", exp, None if s is None else (s.get("store") or {}).get(item))
    for sid, exp in (expected.get("decisions") or {}).items():
        s = by_id.get(sid)
        row(sid, "decision", exp, None if s is None else s.get("decision"))
    for sid in decide_ids:
        if sid not in (expected.get("decisions") or {}):
            row(sid, "decision-expected-for-decide-step", True, False)
    table_positive = sum(len(cs or []) for a in exp_calls.values() for cs in (a or {}).values())
    row("-", "positive-calls-compared", table_positive, compared_positive)
    if not expected.get("no_positive_calls"):
        row("-", "positive-calls>0", True, table_positive > 0)
    return {"pass": all(r["ok"] for r in rows), "rows": rows, "n_rows": len(rows),
            "n_fail": sum(not r["ok"] for r in rows), "expected_positive_calls": table_positive}


def main():
    raw = load_raw(sys.argv[1])
    with open(sys.argv[2]) as f:
        exp = yaml.safe_load(f)
    with open(sys.argv[3]) as f:
        sc = yaml.safe_load(f)
    res = judge(raw, exp, sc)
    for r in res["rows"]:
        if not r["ok"]:
            print("FAIL", r["step"], r["what"], "expected", json.dumps(r["expected"]), "observed", json.dumps(r["observed"]))
    print(("PASS" if res["pass"] else "FAIL"), f"{res['n_rows']} rows, {res['n_fail']} failing")
    return 0 if res["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
