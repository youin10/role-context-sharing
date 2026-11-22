"""Emit the host sweep phase times in milliseconds, preserving repetition order."""
import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median

raw = Path(__file__).resolve().parents[3] / "records/core/notif-host/sweep/sweep-raw.jsonl"
if hashlib.sha256(raw.read_bytes()).hexdigest() != "da13c28fe3f7ddf167b197d8ee2b3350733a47a84c480b6a74d80efedb08cb88":
    raise ValueError("Host sweep digest mismatch")
groups = defaultdict(dict)
for line in raw.read_text().splitlines():
    row = json.loads(line)
    dims = row["dims"]
    key = dims["R"], dims["M"], dims["C"], row["arm"]
    if not row["correct"] or row["rep"] in groups[key]:
        raise ValueError(f"Unexpected observation for {key}")
    groups[key][row["rep"]] = row["times_s"]

writer = csv.writer(sys.stdout, lineterminator="\n")
writer.writerow(["N", "K", "Q", "arm", "phase", *(f"rep{i}_ms" for i in range(1, 6)),
                 "median_ms", "min_ms", "max_ms"])
phases = {"D": ["parse", "check", "generate", "events", "redeploy_generate", "redeploy_stage"],
          "A": ["helper_expand_targets", "initial_load", "events", "redeploy_dispatch"]}
for (n, k, q, arm), observations in sorted(groups.items()):
    if set(observations) != set(range(1, 6)):
        raise ValueError(f"Incomplete repetitions for {(n, k, q, arm)}")
    for phase in phases[arm]:
        values = [1000 * observations[i][phase] for i in range(1, 6)]
        writer.writerow([n, k, q, arm, phase, *values, median(values), min(values), max(values)])
