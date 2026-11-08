"""Runs a set of scenario/arm/repetition cells, judges each run and writes a summary.

  run_matrix.py --label <label> [--reps 3] [--jobs 3] [--scenarios TR1,TR2]
  run_matrix.py --label <label> --negative [--jobs 3]
A failed run is kept. A rerun uses a new label. Parallel jobs use separate Compose projects and
MQTT ports on one host; only functional outcomes are judged.
"""
import argparse
import concurrent.futures
import json
import os
import subprocess
import queue
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tools.run_one import tree_hash  # noqa: E402
from wcs.core import CORE  # noqa: E402

PY = sys.executable
BASE_PORT = int(os.environ.get("WCS_MQTT_PORT", "18883"))
SCENARIOS = ["TR1", "TR2", "TR3", "TR4", "TR5", "TR6", "TR7", "C1", "C2", "N1", "N2"]
ARMS = ["D", "A", "H"]
NEGATIVE = [("TR1", "drop-retract", ARMS), ("TR2", "stale-config", ARMS), ("TR3", "stale-config", ARMS),
            ("TR4", "stale-config", ARMS), ("TR5", "stale-config", ARMS), ("TR5", "boundary", ["D", "A"]),
            ("N2", "no-validation", ["D", "A"]), ("TR3", "per-role-retract", ["D"]), ("TR6", "dup-branch", ["D"]),
            ("TR6", "non-transitive", ["D"])]


def snapshot_verify():
    r = subprocess.run([PY, "-B", "tools/snapshot.py", "verify", "cs-core-a255c156de6c"], cwd=CORE,
                       capture_output=True, text=True)
    return r.returncode == 0


def freeze():
    return {k: tree_hash(os.path.join(ROOT, k)) for k in ("config", "sim", "wcs", "tools")}


def run_cell(cell, label, out, ports):
    s, arm, rep, fault = cell
    port = ports.get()
    try:
        cmd = [PY, "-B", "tools/run_one.py", "--scenario", s, "--arm", arm, "--rep", str(rep), "--label", label]
        if fault:
            cmd += ["--fault", fault]
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env={**os.environ, "WCS_MQTT_PORT": str(port)})
    finally:
        ports.put(port)
    name = f"{s}-{arm}-{rep}" + (f"-{fault}" if fault else "")
    run_dir = os.path.join(out, name)
    verdict = {"run": name, "pass": False, "fails": [{"code": "NO_EVENTS", "detail": r.stderr[-400:]}]}
    if os.path.exists(os.path.join(run_dir, "events.jsonl")):
        j = subprocess.run([PY, "-B", "tools/judge.py", run_dir], cwd=ROOT, capture_output=True, text=True)
        verdict = json.loads(j.stdout) if j.stdout else {"run": name, "pass": False,
                                                         "fails": [{"code": "JUDGE_ERROR", "detail": j.stderr[-400:]}]}
    with open(os.path.join(run_dir, "judge.json"), "w") as f:
        json.dump(verdict, f, indent=1, ensure_ascii=False)
    return {"run": name, "scenario": s, "arm": arm, "rep": rep, "fault": fault, "pass": verdict["pass"],
            "fail_codes": sorted({x["code"] for x in verdict["fails"]}), "rc": r.returncode,
            "stdout": r.stdout.strip()[-200:], "stderr": r.stderr.strip()[-600:]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--scenarios", default=",".join(SCENARIOS))
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--negative", action="store_true")
    a = ap.parse_args()
    out = os.path.join(ROOT, "records", a.label)
    if os.path.exists(out):
        sys.exit(f"refusing to overwrite {out}")
    os.makedirs(out)
    before = {"core_snapshot_ok": snapshot_verify(), "hashes": freeze(),
              "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if not before["core_snapshot_ok"]:
        sys.exit("core snapshot verification failed")
    if a.negative:
        cells = [(s, arm, 1, fault) for s, fault, arms in NEGATIVE for arm in arms]
    else:
        cells = [(s, arm, rep, None) for rep in range(1, a.reps + 1) for s in a.scenarios.split(",")
                 for arm in a.arms.split(",")]
    ports = queue.Queue()
    for i in range(a.jobs):
        ports.put(BASE_PORT + i)
    rows = []
    with concurrent.futures.ThreadPoolExecutor(a.jobs) as pool, open(os.path.join(out, "matrix.log"), "w") as log:
        futures = [pool.submit(run_cell, c, a.label, out, ports) for c in cells]
        for fut in concurrent.futures.as_completed(futures):
            row = fut.result()
            rows.append(row)
            log.write(json.dumps(row, ensure_ascii=False) + "\n")
            log.flush()
    rows.sort(key=lambda r: r["run"])
    after = {"core_snapshot_ok": snapshot_verify(), "hashes": freeze(),
             "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    summary = {"label": a.label, "negative": a.negative, "runs": len(rows), "passed": sum(r["pass"] for r in rows),
               "unchanged_inputs": before["hashes"] == after["hashes"], "before": before, "after": after, "rows": rows}
    with open(os.path.join(out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1, ensure_ascii=False)
    print(a.label, summary["passed"], "/", summary["runs"], "inputs unchanged:", summary["unchanged_inputs"])


if __name__ == "__main__":
    main()
