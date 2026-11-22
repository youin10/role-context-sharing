"""Major 3 summary from rows.jsonl only. Times in ms; warm-up rep 0 excluded.

  python -B summarize.py <out_dir>
"""
import json, os, statistics, sys


def stat(v):
    return {"median": statistics.median(v), "min": min(v), "max": max(v), "values": v}


def build(out):
    rows = [json.loads(l) for l in open(os.path.join(out, "rows.jsonl"))]
    m = [r for r in rows if not r["warmup"]]
    S = {"measured_reps": len({r["rep"] for r in m}), "all_match_expected": all(all(r["matches_expected"]) for r in rows), "arms": {}}
    for arm in ("D", "A"):
        sp = sorted([r for r in m if r["arm"] == arm and r["mode"] == "split"], key=lambda r: r["rep"])
        wh = sorted([r for r in m if r["arm"] == arm and r["mode"] == "whole"], key=lambda r: r["rep"])
        rounds = [stat([r["times_s"][k] * 1e3 for r in sp]) for k in range(4)]
        sums = [sum(r["times_s"]) * 1e3 for r in sp]
        whole = [r["times_s"][0] * 1e3 for r in wh]
        first = sp[0]
        per_round_counts = []
        for k in range(4):
            calls = first["per"][k]["calls"]
            per_round_counts.append({"app_calls_total": sum(len(v) for v in calls.values()),
                                     "app_calls_per_consumer": {c: len(v) for c, v in calls.items()},
                                     "kinds": sorted({x[0] for v in calls.values() for x in v}),
                                     "probe_delta": first["per"][k]["probe_delta"],
                                     "counts_identical_all_reps": all(r["per"][k]["probe_delta"] == first["per"][k]["probe_delta"]
                                                                      and r["per"][k]["calls"] == calls for r in sp)})
        S["arms"][arm] = {"round_ms": rounds, "sum_of_rounds_ms": stat(sums), "whole_ms": stat(whole),
                          "sum_minus_whole_median_ms": statistics.median(sums) - statistics.median(whole),
                          "per_round_counts": per_round_counts,
                          "whole_probe_delta": wh[0]["per"][0]["probe_delta"],
                          "whole_counts_identical_all_reps": all(r["per"][0]["probe_delta"] == wh[0]["per"][0]["probe_delta"] for r in wh),
                          "sum_of_round_probe_equals_whole": {x: sum(pr["probe_delta"][x] for pr in per_round_counts) == wh[0]["per"][0]["probe_delta"][x]
                                                              for x in wh[0]["per"][0]["probe_delta"]}}
    return S


def md(S):
    names = ["1 무통지", "2 Assert", "3 Update", "4 Retract"]
    L = ["# Major 3 보조 라운드 계측 요약 — rows.jsonl에서 자동 생성\n",
         f"측정 반복 {S['measured_reps']}회(예열 1회 제외), 모든 행 기대 일치: {S['all_match_expected']}. 단위 ms, 중앙값 [최소, 최대].\n"]
    for arm, A in S["arms"].items():
        L += [f"## {arm}", "", "| 라운드 | 시간 | 응용 호출 합(소비자 4) | 종류 | 메시지·카운터 증분 |", "|---|---|---|---|---|"]
        for k in range(4):
            s, c = A["round_ms"][k], A["per_round_counts"][k]
            L.append(f"| {names[k]} | {s['median']:.4f} [{s['min']:.4f}, {s['max']:.4f}] | {c['app_calls_total']} | {','.join(c['kinds']) or '없음'} | {json.dumps(c['probe_delta'])} |")
        a, w = A["sum_of_rounds_ms"], A["whole_ms"]
        L += ["", f"- 네 라운드 합: {a['median']:.4f} [{a['min']:.4f}, {a['max']:.4f}]",
              f"- 미분할(16건 한 타이머): {w['median']:.4f} [{w['min']:.4f}, {w['max']:.4f}]",
              f"- 합 중앙값 − 미분할 중앙값: {A['sum_minus_whole_median_ms']:.4f}",
              f"- 라운드 카운터 합 = 미분할 카운터: {A['sum_of_round_probe_equals_whole']}", ""]
        for k in range(4):
            L.append(f"- 라운드 {k + 1} 전체 반복값: " + ", ".join(f"{v:.4f}" for v in A["round_ms"][k]["values"]))
        L.append("- 미분할 전체 반복값: " + ", ".join(f"{v:.4f}" for v in w["values"]))
        L.append("")
    return "\n".join(L) + "\n"


def main():
    out = sys.argv[1]
    S = build(out)
    json.dump(S, open(os.path.join(out, "summary.json"), "w"), indent=1, ensure_ascii=False)
    open(os.path.join(out, "summary.md"), "w").write(md(S))
    print("wrote", out)


if __name__ == "__main__":
    main()
