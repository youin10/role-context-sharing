"""Judges one run directory from its raw events against config/expected.

Reads only events.jsonl, the expected table and the topology file; it does not import the runner.
Report values are checked against the sampled scene poses.
  judge.py <run_dir>
Prints a JSON verdict; exit 1 on any failed check.
"""
import argparse
import json
import math
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARRIVAL = 0.2
HELD = 0.05
STATIONARY = 0.02
RAISED_Z = 0.3
ZONE_CELL = "apron"
DISPLAY = {"RobotLocatedAt": "node", "ZoneStatus": "congestion", "RobotStopped": "elapsedSeconds",
           "CargoCarriedBy": "robot"}


def cell_of(topology, x, y):
    for band in topology["y_bands"]:
        lo, hi = band["range"]
        if lo <= y < hi:
            for (xlo, xhi), name in zip(topology["x_bands"], band["cells"]):
                if xlo <= x < xhi:
                    return name
    return None


def compact(context, value):
    return None if value is None else value[DISPLAY[context]]


def report_value(ev):
    return "DELETE" if ev["value"] is None else compact(ev["context"], ev["value"])


def timeline_key(ev):
    r = ev["rec"]
    if r == "report":
        return ["report", ev["context"], ev["instance"], report_value(ev)]
    if r == "notify":
        return ["notify", ev["agent"], ev["kind"], ev["instance"]]
    if r == "decision":
        return ["decision", ev["task"], ev["outcome"]]
    if r == "command":
        return ["command", ev["robot"], ev["task"]]
    if r == "arrived":
        return ["arrived", ev["task"]]
    if r == "change" and ev["phase"] == "applied":
        return ["change", ev["id"]]
    if r == "refused":
        return ["refused", ev["id"]]
    return None


def observed_mismatch(ev, sample, samples, topology):
    """Returns a reason when a report disagrees with the sampled scene."""
    context, instance, value = ev["context"], ev["instance"], ev["value"]
    poses = sample["poses"]
    if context == "RobotLocatedAt":
        x, y, _ = poses[instance]
        return None if cell_of(topology, x, y) == value["node"] else "cell"
    if context == "ZoneStatus":
        count = sum(1 for p in poses.values() if cell_of(topology, p[0], p[1]) == ZONE_CELL)
        return None if count == value["congestion"] else "congestion"
    if context == "CargoCarriedBy":
        x, y, z = sample["cargo"][instance]
        if value is None:
            return None if z < RAISED_Z else "cargo still raised"
        rx, ry, _ = poses[value["robot"]]
        return None if z >= RAISED_Z and math.hypot(rx - x, ry - y) <= 0.3 else "holder"
    if context == "RobotStopped":
        before = [s for s in samples if s["seq"] <= sample["seq"]]
        if value is None:
            if len(before) < 2:
                return "no motion"
            a, b = before[-2]["poses"][instance], before[-1]["poses"][instance]
            return None if math.hypot(a[0] - b[0], a[1] - b[1]) > 0 else "no motion"
        x, y, _ = poses[instance]
        window = [s for s in before if s["t_sim"] >= sample["t_sim"] - value["elapsedSeconds"]]
        spread = max(math.hypot(s["poses"][instance][0] - x, s["poses"][instance][1] - y) for s in window)
        return None if spread <= STATIONARY else "not stationary"
    return "unknown context"


def judge(events, exp, topology):
    fails = []

    def check(cond, code, detail=None):
        if not cond:
            fails.append({"code": code, "detail": detail})

    by = {}
    for ev in events:
        by.setdefault(ev["rec"], []).append(ev)
    arm = by["start"][0]["arm"]
    end = by.get("end", [{}])[-1]
    samples = by.get("sample", [])
    check(end.get("status") == "ok", "STATUS", end.get("status"))
    check(samples and all(a["t_sim"] < b["t_sim"] for a, b in zip(samples, samples[1:])), "SIM_TIME")
    check(not end.get("outside_report_cfg"), "OUTSIDE_REPORT_CFG", end.get("outside_report_cfg"))

    codes = [item["code"] for e in by.get("rejected", []) for item in e["items"]]
    check(codes == exp.get("rejected", []), "REJECTED", codes)
    refused = {e["id"]: e["code"] for e in by.get("refused", [])}
    check(refused == exp.get("refused", {}).get(arm, {}), "REFUSED", refused)

    reports = {}
    for ev in by.get("report", []):
        reports.setdefault(f"{ev['context']}/{ev['instance']}", []).append(report_value(ev))
    check(reports == exp["reports"], "REPORTS", reports)

    last_sample = None
    for ev in events:
        if ev["rec"] == "sample":
            last_sample = ev
        elif ev["rec"] == "report":
            reason = observed_mismatch(ev, last_sample, samples, topology)
            check(reason is None, "REPORT_NOT_OBSERVED", [ev["seq"], reason])

    notes = {a: [] for a in exp["notifications"]}
    for e in by.get("notify", []):
        notes.setdefault(e["agent"], []).append([e["kind"], e["instance"], compact(e["context"], e["value"])])
    check(notes == exp["notifications"], "NOTIFICATIONS", notes)

    decisions = [[e["task"], e["outcome"], e["occupants"]] for e in by.get("decision", [])]
    check(decisions == exp["decisions"], "DECISIONS", decisions)
    if "decision_owners" in exp:
        owner, owners = exp["notifications"] and next(iter(exp["notifications"])), []
        for ev in events:
            if ev["rec"] == "owner":
                owner = ev["agent"]
            elif ev["rec"] == "decision":
                owners.append(owner)
        check(owners == exp["decision_owners"], "OWNERS", owners)

    commands = [[e["robot"], e["task"]] for e in by.get("command", [])]
    check(commands == exp["commands"], "COMMANDS", commands)

    arrived = {e["task"]: e for e in by.get("arrived", [])}
    results = {e["task"]: e["result"] for e in by.get("response", []) if "task" in e}
    for task, (robot, x, y) in exp["arrivals"].items():
        check(results.get(task) == "success", "RESPONSE", task)
        ev = arrived.get(task)
        check(ev is not None and ev["robot"] == robot
              and math.hypot(ev["pose"][0] - x, ev["pose"][1] - y) <= ARRIVAL, "ARRIVAL", task)

    for h in exp["held"]:
        hold = next((e for e in by.get("decision", []) if e["task"] == h["task"] and e["outcome"] == "hold"), None)
        rel = next((e for e in by.get("decision", []) if e["task"] == h["task"] and e["outcome"] == "release"), None)
        if hold is None or rel is None:
            check(False, "HELD", f"{h['task']}: missing hold or release")
            continue
        window = [s["poses"][h["robot"]] for s in samples if hold["seq"] <= s["seq"] <= rel["seq"]]
        spread = max((math.hypot(p[0] - window[0][0], p[1] - window[0][1]) for p in window), default=None)
        check(spread is not None and spread <= HELD, "HELD_MOVED", spread)
        check(rel["t_sim"] - hold["t_sim"] >= h["min_sim_s"], "HELD_SHORT", rel["t_sim"] - hold["t_sim"])
        after = [s["poses"][h["robot"]] for s in samples if s["seq"] > rel["seq"]]
        moved = max((math.hypot(p[0] - window[-1][0], p[1] - window[-1][1]) for p in after), default=0.0)
        check(moved >= 1.0, "NOT_RELEASED_MOVE", moved)

    for item in exp.get("never_released", []):
        check(not any(e["task"] == item["task"] and e["outcome"] != "hold" for e in by.get("decision", [])), "RELEASED")
        first = samples[0]["poses"][item["robot"]] if samples else [0, 0, 0]
        spread = max((math.hypot(s["poses"][item["robot"]][0] - first[0], s["poses"][item["robot"]][1] - first[1])
                      for s in samples), default=None)
        check(spread is not None and spread <= HELD, "HELD_MOVED", spread)

    co = exp.get("co_occupied")
    if co:
        both = any(all(cell_of(topology, s["poses"][r][0], s["poses"][r][1]) in co["cells"] for r in co["robots"])
                   for s in samples)
        check(both == co["expected"], "CO_OCCUPIED", both)

    for name, want in exp.get("checkpoints", {}).items():
        got = next((e for e in by.get("checkpoint", []) if e["name"] == name), None)
        if got is None:
            check(False, "CHECKPOINT", name)
            continue
        check(all(got["store"].get(k) == v for k, v in want.get("store", {}).items()), "CHECKPOINT_STORE", name)
        check(all(got["views"].get(a) == v for a, v in want.get("views", {}).items()), "CHECKPOINT_VIEW", name)

    keys = [timeline_key(e) for e in events if timeline_key(e)]
    pos = 0
    for want in exp["timeline"]:
        while pos < len(keys) and keys[pos] != want:
            pos += 1
        check(pos < len(keys), "TIMELINE", want)
        pos += 1

    for ch in exp["changes"]:
        applied = [e for e in by.get("change", []) if e["id"] == ch["id"] and e["phase"] == "applied"]
        if not applied or (applied[0].get("meta") or {}).get("skipped"):
            check(False, "CHANGE_NOT_APPLIED", ch["id"])
            continue
        at = applied[0]["seq"]
        state = next(e for e in by["state"] if e["seq"] > at)
        got = {a: [] for a in ch["notifications"]}
        for e in by.get("notify", []):
            if at < e["seq"] < state["seq"]:
                got.setdefault(e["agent"], []).append([e["kind"], e["instance"], compact(e["context"], e["value"])])
        check(got == ch["notifications"], "CHANGE_NOTIFICATIONS", {ch["id"]: got})
        check(all(state["views"].get(a) == v for a, v in ch.get("views", {}).items()), "CHANGE_VIEW", {ch["id"]: state["views"]})
        robots = ch.get("no_reports_since_quiet", [])
        if robots:
            quiet = [e for e in by.get("quiet", []) if e["seq"] < at]
            check(bool(quiet), "NO_QUIET_GATE", ch["id"])
            if quiet:
                extra = [e for e in by.get("report", []) if e["instance"] in robots and quiet[-1]["seq"] < e["seq"] < state["seq"]]
                check(not extra, "REPORT_IN_WINDOW", {ch["id"]: len(extra)})

    check(end.get("store") == exp["final_store"], "FINAL_STORE", end.get("store"))
    check(end.get("views") == exp["final_views"], "FINAL_VIEWS", end.get("views"))
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    a = ap.parse_args()
    with open(os.path.join(a.run_dir, "events.jsonl")) as f:
        events = [json.loads(line) for line in f]
    scenario = next(e["scenario"] for e in events if e["rec"] == "start")
    with open(os.path.join(ROOT, "config", "expected", scenario + ".yml")) as f:
        exp = yaml.safe_load(f)
    with open(os.path.join(ROOT, "config", "topology.yml")) as f:
        topology = yaml.safe_load(f)
    fails = judge(events, exp, topology)
    print(json.dumps({"run": os.path.basename(a.run_dir.rstrip("/")), "pass": not fails, "fails": fails}, ensure_ascii=False))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
