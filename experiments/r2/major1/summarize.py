"""Build summary.json / summary.md of a Major 1 run from its raw JSONL only.

  python -B summarize.py <run_dir>
Times in the summary are milliseconds; statistics over the measured repetitions (warm-up
rep 0 excluded): median, min, max, and every value in repetition order.
"""
import json, os, statistics, sys

KEYS = ["F.parse", "F.check", "F.generate", "I.parse", "I.product", "I.readdecl"]


def load(run_dir):
    driver = [json.loads(l) for l in open(os.path.join(run_dir, "driver.jsonl"))]
    rows = {}
    for d in driver:
        p = os.path.join(run_dir, d["config"] + ".jsonl")
        rows[d["config"]] = [json.loads(l) for l in open(p)] if os.path.exists(p) else []
    return driver, rows


def stat(vals):
    return {"median": statistics.median(vals), "min": min(vals), "max": max(vals), "values": vals} if vals else None


def order_split(reps):
    """I/F parse ratio separated by which parse ran first in the repetition; balanced estimate =
    sqrt(median(F first) * median(I first)) (the order effect cancels if it is symmetric)."""
    f = [r["times_s"]["I.parse"] / r["times_s"]["F.parse"] for r in reps if r["order"][0] == "F"]
    i = [r["times_s"]["I.parse"] / r["times_s"]["F.parse"] for r in reps if r["order"][0] == "I"]
    if not f or not i:
        return None
    return {"F_first": stat(f), "I_first": stat(i), "balanced": (statistics.median(f) * statistics.median(i)) ** 0.5}


def ms(r, k):
    if k.startswith("I.") and k != "I.parse":
        v = r.get(k + "_s")
    else:
        v = r["times_s"].get(k)
    return None if v is None else v * 1e3


def build(run_dir):
    driver, rows = load(run_dir)
    out = []
    for d in driver:
        rs = rows[d["config"]]
        reps = [r for r in rs if r["kind"] == "rep" and not r["warmup"]]
        warm = [r for r in rs if r["kind"] == "rep" and r["warmup"]]
        stop = [r for r in rs if r["kind"] == "stopped"]
        res = [r for r in rs if r["kind"] == "result"]
        fam, m = d["config"].split("-m")
        e = {"config": d["config"], "family": fam, "m": int(m), "driver_status": d["status"], "driver_reason": d.get("reason"),
             "elapsed_s": d.get("elapsed_s"), "peak_rss_polled_bytes": d.get("peak_rss_polled_bytes"),
             "measured_reps": len(reps),
             "warmup_ms": {k: ms(warm[0], k) for k in KEYS} if warm else None,
             "ms": {k: stat([ms(r, k) for r in reps if ms(r, k) is not None]) for k in KEYS},
             "overhead_ratio_I_over_F_parse": stat([r["times_s"]["I.parse"] / r["times_s"]["F.parse"] for r in reps]),
             "overhead_by_order": order_split(reps),
             "product_share_of_I_parse": stat([r["I.product_s"] / r["times_s"]["I.parse"] for r in reps]),
             "maxrss_bytes": max([r["maxrss_bytes"] for r in rs if "maxrss_bytes" in r], default=None)}
        if stop:
            s = stop[0]
            e["stopped"] = {"rep": s["rep"], "reason": s["reason"], "times_ms": {k: v * 1e3 for k, v in s["times_s"].items()},
                            "maxrss_bytes": s["maxrss_bytes"]}
        if res:
            r = res[0]
            e.update({"expected": r["expected"], "counts": r["counts"], "checks": r["checks"], "ok": r["ok"],
                      "identity": r["identity"]["identical"], "selection": {k: v for k, v in r["selection"].items() if k != "mismatch_examples"}})
        out.append(e)
    by = {(e["family"], e["m"]): e for e in out}
    contrast = []
    for (fam, m), e in sorted(by.items()):
        if fam == "OR" and ("AND", m) in by and e["ms"]["F.parse"] and by[("AND", m)]["ms"]["F.parse"]:
            a = by[("AND", m)]
            contrast.append({"m": m, "OR_F.parse_median_ms": e["ms"]["F.parse"]["median"], "AND_F.parse_median_ms": a["ms"]["F.parse"]["median"],
                             "contrast_difference_estimate_ms": e["ms"]["F.parse"]["median"] - a["ms"]["F.parse"]["median"],
                             "OR_I.product_median_ms": e["ms"]["I.product"]["median"], "AND_I.product_median_ms": a["ms"]["I.product"]["median"]})
    return {"run_dir": os.path.basename(os.path.normpath(run_dir)), "configs": out, "or_and_parse_contrast": contrast}


def fmt(x, nd=3):
    return "—" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


def md(S):
    L = [f"# Major 1 요약 ({S['run_dir']}) — raw에서 자동 생성\n",
         "단위 ms. 중앙값 [최소, 최대], 예열 1회 제외 측정 반복. F = 동결본, I = 계측 사본. F.generate는 내부 check를 포함하므로 F.check와 합산하지 않는다.\n",
         "| 설정 | 상태 | 반복 | 원자 | 전개 절(역할별) | 최종 대안/소비자 | flows | F.parse | F.check | F.generate | I.parse | I.product | I.readdecl | I/F 비 F선행·I선행·균형 | 동일성 | 선택 일치 |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for e in S["configs"]:
        def c(k):
            s = e["ms"].get(k)
            return "—" if not s else f"{s['median']:.4g} [{s['min']:.4g}, {s['max']:.4g}]"
        cnt = e.get("counts", {})
        rd = cnt.get("expanded_reads_per_role", {})
        fin = cnt.get("final_alternatives_per_consumer", {})
        ob = e["overhead_by_order"]
        sel = e.get("selection")
        L.append(f"| {e['config']} | {e['driver_status']} | {e['measured_reps']} | {cnt.get('atoms_in_text', '—')} | "
                 f"{'/'.join(str(v) for v in rd.values()) or '—'} | {sorted(set(fin.values())) if fin else '—'} | {cnt.get('flows', '—')} | "
                 f"{c('F.parse')} | {c('F.check')} | {c('F.generate')} | {c('I.parse')} | {c('I.product')} | {c('I.readdecl')} | "
                 f"{'—' if not ob else format(ob['F_first']['median'], '.3f') + ' · ' + format(ob['I_first']['median'], '.3f') + ' · ' + format(ob['balanced'], '.3f')} | {e.get('identity', '—')} | "
                 f"{'—' if not sel else str(sel['mismatches'] == 0) + f' ({sel['cases']}사례)'} |")
    L += ["", "## 중단·미시작", ""]
    for e in S["configs"]:
        if e["driver_status"] != "ok":
            L.append(f"- {e['config']}: {e['driver_status']} {e.get('driver_reason') or ''} {json.dumps(e.get('stopped'), ensure_ascii=False) if e.get('stopped') else ''}")
    L += ["", "## OR−AND 전체 파싱 대조 차(추정, 정규화 단독 계측 아님)", "",
          "| m | OR F.parse | AND F.parse | 대조 차(추정) | OR I.product | AND I.product |", "|---|---|---|---|---|---|"]
    for x in S["or_and_parse_contrast"]:
        L.append(f"| {x['m']} | {x['OR_F.parse_median_ms']:.4g} | {x['AND_F.parse_median_ms']:.4g} | {x['contrast_difference_estimate_ms']:.4g} | "
                 f"{x['OR_I.product_median_ms']:.4g} | {x['AND_I.product_median_ms']:.4g} |")
    L += ["", "## 모든 반복값 (ms, 반복 순서)", ""]
    for e in S["configs"]:
        for k in ("F.parse", "F.check", "F.generate", "I.parse", "I.product"):
            s = e["ms"].get(k)
            if s:
                L.append(f"- {e['config']} {k}: " + ", ".join(f"{v:.4g}" for v in s["values"]))
    return "\n".join(L) + "\n"


def main():
    run_dir = sys.argv[1]
    S = build(run_dir)
    json.dump(S, open(os.path.join(run_dir, "summary.json"), "w"), indent=1, ensure_ascii=False)
    open(os.path.join(run_dir, "summary.md"), "w").write(md(S))
    print("wrote", os.path.join(run_dir, "summary.json"))


if __name__ == "__main__":
    main()
