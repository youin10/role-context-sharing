#!/usr/bin/env bash
# Repeated live runs of selected scenarios (same procedure as final.sh), D and A, 3 repetitions,
# sequential. Refuses to run unless the core snapshot equals the given one. Where an entry table
# inputs/expected/<scenario>-entries.yml exists, check_entries.py is run on each run's logs.
#   bash live/scenario.sh <cs-core-ID> <label> <attempt> <scenario>...
# Output: live/runs/<label>-<snapshot12>/<attempt>/ with live-snapshot.tar.gz, core-tree.json,
# per-run directories, matrix.log, summary.{json,md}. Never overwrites an attempt.
set -uo pipefail
cd "$(dirname "$0")/.."
SNAP="$1"; LABEL="$2"; ATT="$3"; shift 3
ROOT="live/runs/${LABEL}-$(echo "${SNAP#cs-core-}" | cut -c1-12)/$ATT"
if [ -e "$ROOT" ]; then echo "$ROOT exists; use a new attempt label" >&2; exit 2; fi
mkdir -p "$ROOT"
tar --exclude '__pycache__' --exclude 'runs' -czf "$ROOT/live-snapshot.tar.gz" live
shasum -a 256 "$ROOT/live-snapshot.tar.gz" > "$ROOT/live-snapshot.tar.gz.sha256"
python3 -c "import sys,json; sys.path.insert(0,'tools'); import snapshot; f=snapshot.tree('.'); print(json.dumps({'tree_digest': snapshot.digest(f), 'n_files': len(f)}))" > "$ROOT/core-tree.json"
FAIL=0
for rep in 1 2 3; do
  for s in "$@"; do
    for arm in d a; do
      CMD=(python3 live/run.py --arm "$arm" --scenario "$s" --expected "$s" --rep "$rep" --label "$LABEL"
           --out-root "$ROOT" --expect-snapshot "$SNAP")
      echo "$(date +%H:%M:%S) ${CMD[*]}" >> "$ROOT/matrix.log"
      if ! "${CMD[@]}" >> "$ROOT/matrix.log" 2>&1; then FAIL=$((FAIL+1)); echo "FAILED $arm $s r$rep" >> "$ROOT/matrix.log"; fi
      if [ -f "inputs/expected/$s-entries.yml" ]; then
        RUN=$(ls -td "$ROOT/$LABEL-$arm-${s//\//_}-r$rep-"* | head -1)
        ECMD=(docker run --rm --network none -v "$PWD/live/check_entries.py:/j/check_entries.py:ro"
              -v "$PWD/inputs:/inputs:ro" -v "$PWD/$RUN:/run" rcs-experiments:jazzy
              python3 -I /j/check_entries.py /run "/inputs/expected/$s-entries.yml")
        echo "$(date +%H:%M:%S) ${ECMD[*]}" >> "$ROOT/matrix.log"
        if ! "${ECMD[@]}" >> "$ROOT/matrix.log" 2>&1; then FAIL=$((FAIL+1)); echo "FAILED entries $arm $s r$rep" >> "$ROOT/matrix.log"; fi
      fi
    done
  done
done
python3 live/summarize.py "$ROOT" >> "$ROOT/matrix.log" 2>&1
echo "failed runs: $FAIL" | tee -a "$ROOT/matrix.log"
exit $FAIL
