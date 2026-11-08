"""Judge sensitivity: applies one defect at a time to a clean run's raw events.

  mutate_nc.py <label> [--rep 1]
Every mutated log must be refused by the judge. Records are read, never rewritten.
"""
import argparse
import copy
import json
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tools.judge import judge  # noqa: E402


def first(events, rec, **match):
    """Returns the index of the first matching record, raising LookupError when there is none."""
    i = _find(events, rec, **match)
    if i is None:
        raise LookupError(rec)
    return i


def _find(events, rec, **match):
    for i, e in enumerate(events):
        if e["rec"] == rec and all(e.get(k) == v for k, v in match.items()):
            return i
    return None


def drop_retract(ev):
    del ev[first(ev, "notify", kind="retract")]


def assert_as_update(ev):
    ev[first(ev, "notify", kind="assert")]["kind"] = "update"


def drop_decision(ev):
    del ev[first(ev, "decision")]


def flip_decision(ev):
    d = ev[first(ev, "decision", outcome="release")]
    d["outcome"] = "hold"


def drop_arrival(ev):
    del ev[first(ev, "arrived")]


def alter_store(ev):
    ev[-1]["store"]["RobotLocatedAt/wheel1"] = {"node": "t_w"}


def view_leak(ev):
    consumer = next(iter(ev[-1]["views"]))
    ev[-1]["views"][consumer]["RobotLocatedAt/hybrid1"] = {"node": "t_e"}


def unobserved_report(ev):
    ev[first(ev, "report", n=2, context="RobotLocatedAt")]["value"] = {"node": "bay_nw"}


def drop_rejection(ev):
    del ev[first(ev, "rejected")]


def accept_refused(ev):
    del ev[first(ev, "refused")]


def stop_while_moving(ev):
    i = first(ev, "report", context="RobotStopped")
    robot = ev[i]["instance"]
    for e in ev[:i][::-1]:
        if e["rec"] == "sample":
            e["poses"][robot][0] += 1.0
            return


def moved_while_held(ev):
    hold = first(ev, "decision", outcome="hold")
    robot = ev[hold]["robot"]
    for e in ev[hold:]:
        if e["rec"] == "sample":
            e["poses"][robot][0] += 1.0
            return


def report_during_change(ev):
    i = first(ev, "change", phase="applied")
    q = first(ev, "quiet")
    robot = ev[q]["robots"][0]
    row = {**ev[i], "rec": "report", "producer": robot, "context": "RobotLocatedAt", "instance": robot,
           "value": {"node": "apron"}, "n": 99, "cause": None}
    row.pop("id"), row.pop("phase"), row.pop("meta", None)
    ev.insert(i, row)


MUTATIONS = [drop_retract, assert_as_update, drop_decision, flip_decision, drop_arrival, alter_store, view_leak,
             unobserved_report, moved_while_held, report_during_change, drop_rejection, accept_refused,
             stop_while_moving]
SCENARIOS = ["TR1", "TR2", "TR3", "TR4", "TR5", "TR6", "TR7", "C1", "C2", "N1", "N2"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("--rep", type=int, default=1)
    a = ap.parse_args()
    with open(os.path.join(ROOT, "config", "topology.yml")) as f:
        topology = yaml.safe_load(f)
    rows = []
    for s in SCENARIOS:
        with open(os.path.join(ROOT, "config", "expected", s + ".yml")) as f:
            exp = yaml.safe_load(f)
        for arm in ("D", "A", "H"):
            run = os.path.join(ROOT, "records", a.label, f"{s}-{arm}-{a.rep}", "events.jsonl")
            with open(run) as f:
                clean = [json.loads(line) for line in f]
            base = not judge(clean, exp, topology)
            for m in MUTATIONS:
                ev = copy.deepcopy(clean)
                try:
                    m(ev)
                except (LookupError, TypeError, IndexError):
                    rows.append({"run": f"{s}-{arm}", "mutation": m.__name__, "result": "not-applicable"})
                    continue
                try:
                    fails = judge(ev, exp, topology)
                    detected, codes = bool(fails), sorted({x["code"] for x in fails})
                except (KeyError, StopIteration, IndexError, TypeError) as e:
                    detected, codes = True, [f"judge-error:{type(e).__name__}"]
                rows.append({"run": f"{s}-{arm}", "mutation": m.__name__,
                             "result": "detected" if detected else "MISSED", "codes": codes, "clean_pass": base})
    out = {"label": a.label, "rep": a.rep, "rows": rows,
           "detected": sum(r["result"] == "detected" for r in rows),
           "missed": sum(r["result"] == "MISSED" for r in rows),
           "not_applicable": sum(r["result"] == "not-applicable" for r in rows)}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    sys.exit(1 if out["missed"] else 0)


if __name__ == "__main__":
    main()
