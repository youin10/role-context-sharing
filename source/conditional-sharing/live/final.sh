#!/usr/bin/env bash
# Final matrix (approved): CT1..CT7-cfg1 + K, T, P1, each D and A, 3 repetitions, sequential.
# Refuses to run unless the core snapshot equals the frozen one given by the core worker.
#   bash live/final.sh <cs-core-ID or tree digest> [attempt label, default a1]
# Output: live/runs/final-<snapshot12>/<attempt>/ with live-snapshot.tar.gz (live sources), core-tree.json
# (core tree digest), per-run directories, matrix.log, summary.{json,md}. Never overwrites an attempt.
set -uo pipefail
cd "$(dirname "$0")/.."
SNAP="$1"; ATT="${2:-a1}"
ROOT="live/runs/final-${SNAP#cs-core-}"; ROOT="${ROOT:0:28}/$ATT"
if [ -e "$ROOT" ]; then echo "$ROOT exists; use a new attempt label" >&2; exit 2; fi
mkdir -p "$ROOT"
# live sources (the core tree is preserved by tools/snapshot.py as snapshots/<id>.tar.gz)
tar --exclude '__pycache__' --exclude 'runs' -czf "$ROOT/live-snapshot.tar.gz" live
shasum -a 256 "$ROOT/live-snapshot.tar.gz" > "$ROOT/live-snapshot.tar.gz.sha256"
python3 -c "import sys,json; sys.path.insert(0,'tools'); import snapshot; f=snapshot.tree('.'); print(json.dumps({'tree_digest': snapshot.digest(f), 'n_files': len(f)}))" > "$ROOT/core-tree.json"
SCEN="contract/CT1 contract/CT2 contract/CT3 contract/CT4 contract/CT5 contract/CT6 contract/CT7-cfg0 contract/CT7-cfg1 K T P1"
FAIL=0
for rep in 1 2 3; do
  for s in $SCEN; do
    for arm in d a; do
      CMD=(python3 live/run.py --arm "$arm" --scenario "$s" --expected "$s" --rep "$rep" --label final
           --out-root "$ROOT" --expect-snapshot "$SNAP")
      echo "$(date +%H:%M:%S) ${CMD[*]}" >> "$ROOT/matrix.log"
      if ! "${CMD[@]}" >> "$ROOT/matrix.log" 2>&1; then FAIL=$((FAIL+1)); echo "FAILED $arm $s r$rep" >> "$ROOT/matrix.log"; fi
    done
  done
done
python3 live/summarize.py "$ROOT" >> "$ROOT/matrix.log" 2>&1
echo "failed runs: $FAIL" | tee -a "$ROOT/matrix.log"
exit $FAIL
