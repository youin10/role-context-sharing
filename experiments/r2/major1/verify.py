"""Re-check a Major 1 run: recompute every statistic from raw JSONL with independent code and
compare with summary.json; check repetition counts, stop records, identity, clause counts
(also against the input MANIFEST written before measurement) and selection results.
Exit 0 only if everything holds.

  python -B verify.py <run_dir>
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def med(v):
    s = sorted(v)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def main():
    run = sys.argv[1]
    S = json.load(open(os.path.join(run, "summary.json")))
    man = {c["name"]: c for c in json.load(open(os.path.join(HERE, "inputs", "MANIFEST.json")))["configs"]}
    budget = json.load(open(os.path.join(HERE, "budget.json")))
    bad = []
    import hashlib
    mf = json.load(open(os.path.join(HERE, "inputs", "MANIFEST.json")))["files"]
    for fn, h in mf.items():
        if hashlib.sha256(open(os.path.join(HERE, "inputs", fn), "rb").read()).hexdigest() != h:
            bad.append(f"input {fn}: sha256 differs from MANIFEST")
    if len(mf) != len([x for x in os.listdir(os.path.join(HERE, "inputs")) if x != "MANIFEST.json"]):
        bad.append("inputs dir has files outside MANIFEST")
    driver = [json.loads(l) for l in open(os.path.join(run, "driver.jsonl"))]
    seen = {e["config"]: e for e in S["configs"]}
    for d in driver:
        name = d["config"]
        e = seen.get(name)
        if e is None:
            bad.append(f"{name}: missing in summary"); continue
        p = os.path.join(run, name + ".jsonl")
        rows = [json.loads(l) for l in open(p)] if os.path.exists(p) else []
        reps = [r for r in rows if r["kind"] == "rep" and r["rep"] > 0]
        if d["status"] == "ok":
            if len(reps) != budget["repetitions"]["measured"]:
                bad.append(f"{name}: {len(reps)} measured reps")
            res = [r for r in rows if r["kind"] == "result"]
            if len(res) != 1 or not res[0]["ok"]:
                bad.append(f"{name}: result missing or not ok")
            else:
                r = res[0]
                if r["counts"]["expanded_reads_total"] != man[name]["expected"]["expanded_reads_total"]:
                    bad.append(f"{name}: expanded reads vs pre-written manifest")
                if set(r["counts"]["final_alternatives_per_consumer"].values()) != {man[name]["expected"]["final_alternatives_per_consumer"]}:
                    bad.append(f"{name}: final alternatives vs manifest")
                if not r["identity"]["identical"] or r["selection"]["mismatches"] or r["selection"]["sm_rejected"] or r["selection"]["sm_stale"]:
                    bad.append(f"{name}: identity/selection")
            st = [r for r in rows if r["kind"] == "start"]
            if not st or st[0]["org_sha256"] != man[name]["org_sha256"]:
                bad.append(f"{name}: org hash differs from input manifest")
        elif d["status"] == "stopped":
            if not any(r["kind"] == "stopped" for r in rows):
                bad.append(f"{name}: stopped without stop row")
        for k, key in (("F.parse", None), ("F.check", None), ("F.generate", None), ("I.parse", None), ("I.product", "I.product_s"), ("I.readdecl", "I.readdecl_s")):
            vals = [(r[key] if key else r["times_s"].get(k)) for r in reps]
            vals = [v * 1e3 for v in vals if v is not None]
            s = e["ms"].get(k)
            if not vals:
                if s:
                    bad.append(f"{name} {k}: summary has stats without raw")
                continue
            if s is None or s["values"] != vals or s["median"] != med(vals) or s["min"] != min(vals) or s["max"] != max(vals):
                bad.append(f"{name} {k}: summary mismatch")
        if reps:
            ratios = [r["times_s"]["I.parse"] / r["times_s"]["F.parse"] for r in reps]
            if e["overhead_ratio_I_over_F_parse"]["median"] != med(ratios):
                bad.append(f"{name}: overhead ratio mismatch")
            fr = [r["times_s"]["I.parse"] / r["times_s"]["F.parse"] for r in reps if r["order"][0] == "F"]
            ir = [r["times_s"]["I.parse"] / r["times_s"]["F.parse"] for r in reps if r["order"][0] == "I"]
            ob = e["overhead_by_order"]
            if ob["F_first"]["values"] != fr or ob["I_first"]["values"] != ir or abs(ob["balanced"] - (med(fr) * med(ir)) ** 0.5) > 1e-12:
                bad.append(f"{name}: order-split overhead mismatch")
    for x in S["or_and_parse_contrast"]:
        o, a = seen[f"OR-m{x['m']:02d}"], seen[f"AND-m{x['m']:02d}"]
        if x["contrast_difference_estimate_ms"] != o["ms"]["F.parse"]["median"] - a["ms"]["F.parse"]["median"]:
            bad.append(f"contrast m={x['m']} mismatch")
    # family stop rule: nothing started after a stop/abort in the same family
    stopped = set()
    for d in driver:
        fam = d["config"].split("-")[0]
        if fam in stopped and d["status"] not in ("not_started",):
            bad.append(f"{d['config']}: started after family stop")
        if d["status"] in ("stopped", "aborted", "error"):
            stopped.add(fam)
    print(json.dumps({"run": run, "configs": len(driver), "problems": bad}, indent=1, ensure_ascii=False))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
