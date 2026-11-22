# Condition expansion, notification rounds and Table 6 timings

The two supplemental experiments use the public core snapshot `cs-core-a255c156de6c` from package commit `ec54dde46071543f75916328bbdcb53b9c5b3b77`. The Table 6 host sweep used the earlier measurement snapshot `cs-core-9ec4e836cb48`. Its raw records are already in this repository.

Run the commands below from `experiments/r2` in a checkout. Archived-data verification uses only the Python standard library. Running either harness requires PyYAML (measured with Python 3.14.7 and PyYAML 6.0.2) and Major 1 uses POSIX resource accounting and `ps`. The recorded new measurements used an Apple M5 with 10 CPU cores, 32 GiB and macOS 26.7.3 on a shared host. The earlier host sweep used macOS 26.6.2.

## Verify the archived results

```sh
set -eu
shasum -a 256 -c MANIFEST.sha256
python3 -B major1/verify.py major1/raw/m1-run1
python3 -B major3/verify.py major3/raw/m3-run1
out=$(mktemp -d)
python3 -B table6/aggregate.py > "$out/phase-times.csv"
cmp table6/phase-times.csv "$out/phase-times.csv"
```

### Condition expansion (major1)

The 25 synthetic configurations vary the number of condition lines. OR and AND keep the atoms and bindings fixed, DUP puts the OR condition in two roles, and REF uses the reference threshold. The input manifest records expected clause counts and hashes. Each completed configuration has one warm-up and five measured repetitions. Frozen and instrumented parsing alternate order. Generation includes checking. The independent oracle checks selection outcomes after timing.

The archived driver retained 22 completed configurations, the single-call stop at OR m=16 and both unstarted extensions. See `major1/budget.json` for the original limits. The implementation checked the 120-second threshold after each call. The budget also described a combined warm-up threshold, which the harness did not enforce. The largest combined frozen warm-up among completed configurations was 15.9 seconds. The separate dry-run log retains all three deliberately triggered limits. Two dry-run attempts shared the OR-m08 name, so their driver entries distinguish attempts.

### Notification rounds (major3)

The fixed 4/4/4 workload has four rounds of four reports each. Consumers receive no calls, then Assert, Update and Retract in successive rounds. Split and whole runs begin with fresh state. Each split timer measures the complete round of report processing. Round order and prior state are fixed. The archived 84 rows cover both implementations and both timer modes for one warm-up and 20 measured repetitions. All repetition times, including the high D round-four value, remain in the summaries.

### Table 6

[All phase times](table6/phase-times.csv) give the five repetitions in recorded order, their median, minimum and maximum (milliseconds). The script checks the original host sweep SHA-256, correctness flags and repetition identities, then converts seconds to milliseconds. Twelve N/K/Q configurations contribute 120 phase rows and 600 individual times. N, K and Q map to R, M and C in the [host sweep](../../records/core/notif-host/sweep/sweep-raw.jsonl).

| Arm | Raw phase | Timing interval |
|---|---|---|
| D | parse, check | Separate initial parsing and checking measurements |
| D | generate | Initial generation, including its internal check |
| D | redeploy_generate | Revised parsing, checking and generation |
| A | helper_expand_targets | Prepare two sets of rules, write files and compute deployment targets |
| A | initial_load | Initial plan loading and message handling |
| D, A | events | Complete sequence of 4N reports, including routing and receiver processing |
| D | redeploy_stage | Stage the prepared configuration and process its messages |
| A | redeploy_dispatch | Read the change request, load target plans and process messages |

D initial installation was not timed separately. In the two N=1 settings, A reads the change request and finds zero targets. For the displayed Table 6 values use each phase median rounded to three decimals. The supplemental round measurements use a different host OS version and repetition count.

## Rebuild the inputs and run a small smoke test

Use a Python environment with PyYAML installed. Direct all new output to a fresh directory.

```sh
set -eu
export PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0
out=$(mktemp -d)
python3 -B major1/make_inputs.py "$out/inputs"
diff -qr major1/inputs "$out/inputs"
python3 -B major1/make_instrumented.py ../../source/conditional-sharing/src/arms/d/spec.py "$out/instrumented"
diff -qr major1/instrumented "$out/instrumented"
python3 -B major1/driver.py "$out/m1" --only OR-m02
python3 -B major1/summarize.py "$out/m1"
python3 -B major1/verify.py "$out/m1"
python3 -B major3/run_rounds.py "$out/m3" 5
python3 -B major3/summarize.py "$out/m3"
python3 -B major3/verify.py "$out/m3"
```

For the complete measurement, use fresh output directories, omit `--only OR-m02` and change the round repetition argument to `20`. Budget stops and timing values depend on the host. The archived Major 1 child maximum-RSS field uses the native macOS byte unit; on Linux the same resource call returns KiB. The watchdog independently converts the RSS from ps to bytes.

## Release manifest

`MANIFEST.sha256` lists every file in this directory except itself. The release retains both harnesses, inputs, budgets, generated plans, raw measurement and stop records, numeric summaries, and verification programs. The three scripts that locate the core now resolve it relative to this checkout. Two archived driver logs replace interpreter, child-script and input-directory paths with portable arguments relative to the Major 1 directory. The archived round environment uses repository-relative core and sweep paths. These changes affect path metadata only. The per-configuration measurement streams and per-round rows are byte-identical to their measurement copies. Machine diagnostic dumps, private workspace integrity inventories and internal documents are excluded. The CSV and aggregation program derive exclusively from the existing host sweep.
