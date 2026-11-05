#!/usr/bin/env bash
# CT5 core runs (D, A, A-helper) x 3 repetitions against snapshot cs-core-7ba114d5dcf9.
# Usage (from experiments/conditional-sharing): bash results/role-release-ct5-core/run.sh
set -euo pipefail
OUT=results/role-release-ct5-core PY=.venv/bin/python SNAP=cs-core-7ba114d5dcf9
export PYTHONDONTWRITEBYTECODE=1
"$PY" tools/snapshot.py verify "$SNAP" > "$OUT/freeze-before.txt"
for rep in 1 2 3; do
  mkdir -p "$OUT/rep$rep"
  for spec in "D:main:{}" "A:main:{}" 'A:helper:{"a_variant":"helper"}'; do
    arm="${spec%%:*}"; rest="${spec#*:}"; lab="${rest%%:*}"; var="${rest#*:}"
    raw="$OUT/rep$rep/CT5__${arm}__${lab}.jsonl"
    "$PY" -c 'import sys,json; sys.path.insert(0,"runner"); import core_run; core_run.run("inputs/scenarios/contract/CT5.yml", sys.argv[1], json.loads(sys.argv[2]), sys.argv[3], sys.argv[4])' "$arm" "$var" "$raw" "$lab"
    "$PY" runner/judge.py "$raw" inputs/expected/contract/CT5.yml inputs/scenarios/contract/CT5.yml > "${raw%.jsonl}.judge.txt" || true
    echo "rep$rep $arm $lab $(tail -1 "${raw%.jsonl}.judge.txt")"
  done
  "$PY" tools/check_entries.py "$OUT/rep$rep/entries-CT5.json" CT5 > "$OUT/rep$rep/entries-CT5.stdout.txt" || true
  echo "rep$rep entries: $(tr '\n' ' ' < "$OUT/rep$rep/entries-CT5.stdout.txt")"
done
"$PY" tools/snapshot.py verify "$SNAP" > "$OUT/freeze-after.txt"
