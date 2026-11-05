#!/usr/bin/env bash
# Exact commands of one complete core run. Usage: ./run.sh <run_id> [python] [snapshot_id]
# With a snapshot id the tree is verified against the frozen snapshot before and after the run.
set -euo pipefail
cd "$(dirname "$0")"
RUN_ID="$1"; PY="${2:-.venv/bin/python}"; SNAP="${3:-}"
export PYTHONDONTWRITEBYTECODE=1 CS_SNAPSHOT="$SNAP"
mkdir -p results
if [ -n "$SNAP" ]; then "$PY" tools/snapshot.py verify "$SNAP" > "results/$RUN_ID.freeze-before.txt"; fi
set +e
"$PY" runner/run_all.py "$RUN_ID" > "results/$RUN_ID.stdout.txt" 2>&1; RC_ALL=$?
set -e
mkdir -p "results/$RUN_ID"
mv "results/$RUN_ID.stdout.txt" "results/$RUN_ID/run_all.stdout.txt"
[ -n "$SNAP" ] && mv "results/$RUN_ID.freeze-before.txt" "results/$RUN_ID/freeze-before.txt"
RCS="${CS_RCS:-../../../rcs-experiments}"
"$PY" tools/regress_upstream_fixtures.py "$RCS" "results/$RUN_ID/regression-upstream-fixtures.json" > "results/$RUN_ID/regression.stdout.txt" 2>&1 || echo "regression unavailable or failed (see file)" >> "results/$RUN_ID/regression.stdout.txt"
"$PY" tools/edit_cost.py "results/$RUN_ID/edit_cost.json" "results/$RUN_ID/edit-diffs" > "results/$RUN_ID/edit_cost.stdout.txt"
"$PY" tools/check_units.py "results/$RUN_ID/check_units.json" > "results/$RUN_ID/check_units.stdout.txt" || RC_ALL=1
"$PY" tools/check_entries.py "results/$RUN_ID/entries-CT5.json" CT5 > "results/$RUN_ID/entries-CT5.stdout.txt" || RC_ALL=1
"$PY" tools/timing.py "results/$RUN_ID/timing.json" > "results/$RUN_ID/timing.stdout.txt"
"$PY" tools/sweep.py "results/$RUN_ID/sweep" 5 > "results/$RUN_ID/sweep.stdout.txt" || RC_ALL=1
if [ -n "$SNAP" ]; then "$PY" tools/snapshot.py verify "$SNAP" > "results/$RUN_ID/freeze-after.txt" || RC_ALL=1; fi
echo "run_all exit=$RC_ALL" | tee "results/$RUN_ID/exit.txt"
exit $RC_ALL
