"""Re-check Major 3: recompute statistics from rows.jsonl independently, compare with
summary.json, and re-check every row's calls against workload.json (kinds, values, order),
the round counts (16 reports, 4 consumers x 4 robots per notifying round), rep counts.

  python -B verify.py <out_dir>
"""
import json, os, sys


def med(v):
    s = sorted(v); n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def main():
    out = sys.argv[1]
    S = json.load(open(os.path.join(out, "summary.json")))
    W = json.load(open(os.path.join(out, "workload.json")))
    rows = [json.loads(l) for l in open(os.path.join(out, "rows.jsonl"))]
    exp = W["expected_per_consumer_by_round"]
    bad = []
    if [len(x) for x in exp] != [0, 4, 4, 4]:
        bad.append("expected round sizes")
    for r in rows:
        if r["mode"] == "split":
            if len(r["times_s"]) != 4:
                bad.append(f"rep {r['rep']} {r['arm']}: rounds")
            for k in range(4):
                for c, calls in r["per"][k]["calls"].items():
                    if calls != exp[k]:
                        bad.append(f"rep {r['rep']} {r['arm']} round {k + 1} {c}: calls differ")
        else:
            full = [x for k in range(4) for x in exp[k]]
            for c, calls in r["per"][0]["calls"].items():
                if calls != full:
                    bad.append(f"rep {r['rep']} {r['arm']} whole {c}: calls differ")
        if r["arm"] == "D":
            pd = [p["probe_delta"] for p in r["per"]]
            if r["mode"] == "split" and ([p["reports"] for p in pd] != [4, 4, 4, 4] or [p["msgs"] for p in pd] != [0, 16, 16, 16]
                                         or any(p["stale"] or p["rejected"] for p in pd)):
                bad.append(f"rep {r['rep']} D split: report/message counts {pd}")
    m = [r for r in rows if not r["warmup"]]
    reps = sorted({r["rep"] for r in m})
    if len(reps) < 5:
        bad.append("fewer than 5 measured reps")
    for arm in ("D", "A"):
        sp = sorted([r for r in m if r["arm"] == arm and r["mode"] == "split"], key=lambda r: r["rep"])
        wh = sorted([r for r in m if r["arm"] == arm and r["mode"] == "whole"], key=lambda r: r["rep"])
        A = S["arms"][arm]
        for k in range(4):
            v = [r["times_s"][k] * 1e3 for r in sp]
            s = A["round_ms"][k]
            if s["values"] != v or s["median"] != med(v) or s["min"] != min(v) or s["max"] != max(v):
                bad.append(f"{arm} round {k + 1} stats")
        sums = [sum(r["times_s"]) * 1e3 for r in sp]
        whole = [r["times_s"][0] * 1e3 for r in wh]
        if A["sum_of_rounds_ms"]["median"] != med(sums) or A["whole_ms"]["median"] != med(whole) or A["whole_ms"]["values"] != whole:
            bad.append(f"{arm} sum/whole stats")
        if A["sum_minus_whole_median_ms"] != med(sums) - med(whole):
            bad.append(f"{arm} difference")
        if not all(A["sum_of_round_probe_equals_whole"].values()):
            bad.append(f"{arm} round counters do not add up to whole")
    print(json.dumps({"rows": len(rows), "measured_reps": len(reps), "problems": bad[:20], "n_problems": len(bad)}, indent=1))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
