"""Summary of a directory of live runs (stdlib only): per scenario × arm verdicts over the
repetitions, agreement of the observed calls/views/decisions across repetitions, identical
input/plan/source hashes, environment, counts, settle times and disk use.

  python3 live/summarize.py <runs dir> [out.json]     (also writes <runs dir>/summary.md)
"""
import glob
import json
import os
import statistics
import subprocess
import sys


def main():
    root = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(root, "summary.json")
    runs = []
    for m in sorted(glob.glob(os.path.join(root, "*", "manifest.json"))):
        d = os.path.dirname(m)
        man = json.load(open(m))
        j = json.load(open(os.path.join(d, "judge.json"))) if os.path.exists(os.path.join(d, "judge.json")) else None
        nc = json.load(open(os.path.join(d, "nc.json"))) if os.path.exists(os.path.join(d, "nc.json")) else None
        env = {}
        lp = os.path.join(d, "logs", "driver.jsonl")
        if os.path.exists(lp):
            with open(lp) as f:
                env = json.loads(f.readline())
        runs.append({"dir": os.path.basename(d), "man": man, "judge": j, "nc": nc, "env": env})
    groups = {}
    for r in runs:
        groups.setdefault((r["man"]["scenario"], r["man"]["arm"]), []).append(r)
    rows = []
    for (sc, arm), rs in sorted(groups.items()):
        obs = [json.dumps([x for x in (r["judge"] or {}).get("rows", [])], sort_keys=True)
               for r in rs]
        stats = [(r["judge"] or {}).get("stats", {}) for r in rs]
        dts = [s["dt_s"] for st in stats for s in st.get("settle", []) if s.get("dt_s") is not None]
        rows.append({
            "scenario": sc, "arm": arm, "runs": len(rs),
            "pass": sum((r["judge"] or {}).get("verdict") == "PASS" for r in rs),
            "nc_ok": sum(bool(r["nc"] and r["nc"]["ok"]) for r in rs),
            "nc_detected": [r["nc"] and f'{r["nc"]["detected"]}/{r["nc"]["applied"]}' for r in rs],
            "exit_all_zero": all(r["man"].get("exit_codes") and all(v == 0 for v in r["man"]["exit_codes"].values())
                                 for r in rs),
            "reps_identical_observation": len(set(obs)) == 1,
            "same_inputs": len({(r["man"]["scenario_sha256"], r["man"]["expected_sha256"], r["man"]["plan_sha256"],
                                 r["man"]["core_snapshot_sha256"], r["man"]["live_sha256"]) for r in rs}) == 1,
            "expected_positive_calls": stats[0].get("expected_positive_calls"),
            "observed_calls": [s.get("observed_calls") for s in stats],
            "by_kind": stats[0].get("by_kind"), "decisions": [s.get("decisions") for s in stats],
            "rejected": [s.get("rejected") for s in stats],
            "messages_sent": [s.get("messages", {}).get("sent") for s in stats],
            "missing_dup_unsent": [[s.get("messages", {}).get(k) for k in ("missing", "duplicate", "unsent")]
                                   for s in stats],
            "settle_dt_s_median": statistics.median(dts) if dts else None, "settle_dt_s_max": max(dts) if dts else None,
            "wall_s": [r["man"].get("wall_s") for r in rs],
        })
    envs = {(r["man"]["image_id"], r["env"].get("rmw"), tuple(r["man"].get("image_env_probe", []))) for r in runs}
    du = subprocess.run(["du", "-sk", root], capture_output=True, text=True).stdout.split()[0]
    summary = {"root": root, "runs": len(runs), "pass": sum((r["judge"] or {}).get("verdict") == "PASS" for r in runs),
               "nc_ok": sum(bool(r["nc"] and r["nc"]["ok"]) for r in runs),
               "core_snapshots": sorted({r["man"]["core_snapshot_sha256"] for r in runs}),
               "live_snapshots": sorted({r["man"]["live_sha256"] for r in runs}),
               "environments": [list(e[:2]) + [list(e[2])] for e in envs], "disk_kib": int(du), "rows": rows}
    with open(out, "w") as f:
        json.dump(summary, f, indent=1)
    lines = [f"# live runs summary: {root}", "",
             f"runs {summary['runs']}, judge PASS {summary['pass']}, raw NC ok {summary['nc_ok']}, disk {du} KiB", "",
             f"core snapshot(s): {summary['core_snapshots']}", f"live snapshot(s): {summary['live_snapshots']}", "",
             "| scenario | arm | PASS | NC ok | exit 0 | reps identical | same hashes | exp+ | calls | kinds | decisions | rejected | msgs | settle med/max s |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['scenario']} | {r['arm']} | {r['pass']}/{r['runs']} | {r['nc_ok']}/{r['runs']} | "
                     f"{r['exit_all_zero']} | {r['reps_identical_observation']} | {r['same_inputs']} | "
                     f"{r['expected_positive_calls']} | {r['observed_calls']} | {r['by_kind']} | {r['decisions']} | "
                     f"{r['rejected']} | {r['messages_sent']} | {r['settle_dt_s_median']}/{r['settle_dt_s_max']} |")
    with open(os.path.join(root, "summary.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines[:3]))
    return 0 if summary["pass"] == summary["runs"] and summary["nc_ok"] == summary["runs"] else 1


if __name__ == "__main__":
    sys.exit(main())
