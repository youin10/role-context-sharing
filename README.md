# Conditional context sharing — reproducibility package

Reproducibility package for the conditional context sharing, multi-role support, and configuration redeployment evaluation. It packages the cleaned public source snapshot `cs-core-a255c156de6c`, derived from the execution-time snapshot `cs-core-9ec4e836cb48` by the same removal of non-semantic authoring comments and internal workspace references used for the earlier public snapshots. In this version consumers receive the knowledge notifications assert (add a fact), update (revise a supplied fact) and retract (remove a supplied fact), decided by Shared Memory. The evidence of record is the full core run `records/core/notif-host` (Linux container rerun `records/core/notif-docker`) and the 66 ROS 2 runs `records/ros2/final-9ec4e836cb48/a2`, all executed against `cs-core-9ec4e836cb48`. Records of earlier implementation versions are kept for lineage and are not combined with the current records (Provenance notes 3 and 4, `traceability/EVIDENCE-INDEX.md` Section 0). Earlier datasets (the 18-run submission set and the 242-run set) are separate evaluations.

Repository: https://github.com/youin10/role-context-sharing

License: [MIT](LICENSE).

## Layout

| Path | Content |
|---|---|
| `source/conditional-sharing/` | Exact extraction of `snapshots/cs-core-a255c156de6c.tar.gz` (296 files: `src/`, `runner/`, `inputs/`, `tools/`, `upstream/`, `run.sh`, `README.md`, `expected-hashes.json`) plus `live/` extracted from `snapshots/live-snapshot-notif.tar.gz` (with an internal report path removed from `live/README.md`), and `snapshots/` (current core snapshot copy used by `tools/snapshot.py verify`, and the per-file manifests of the execution-time snapshots) |
| `snapshots/` | Frozen archives and hashes. Current: public core archive `cs-core-a255c156de6c.tar.gz` + `.sha256` + `.json`, execution-time manifest `cs-core-9ec4e836cb48.json`, live archive `live-snapshot-notif.tar.gz` + `.sha256`, `core-tree-notif.json`. Earlier versions: `cs-core-486f4f7b6ca3.*` / `cs-core-7ba114d5dcf9.json` / `live-snapshot-role-release.tar.gz` / `core-tree-role-release.json`, and `cs-core-8174f3ee50f2.*` / `cs-core-c6cef8724cd4.json` / `live-snapshot.tar.gz` / `core-tree.json`; each archive contains the judge, inputs and expected tables of its version |
| `records/core/notif-host/` | Core run of record (raw JSONL, judgments, grammar, x1, a_static, NC, judge NC, unit checks, consumer-entry check, edit diffs, timing, sweep, manifest) |
| `records/core/notif-docker/` | Rerun in a Linux container of the snapshot-verified tree; `notif-host-docker-comparison.json` compares the two |
| `records/core/notif-entries-nc/` | Stale-model control of the CT5 consumer-entry check (3/3 fail as intended) |
| `records/core/source-binding-check/` | Separate static check of the source and binding validation (8 cases): `sb-9ec4-1` against `cs-core-9ec4e836cb48` (result, manifest, freeze verification before/after, judge mutations) and `pub-a255-1` against the public snapshot (identical observations); not part of the counted runs (Provenance note 5) |
| `records/core/notif-comparison.json` | Field-by-field comparison of all 166 raw files of `role-release-host` and `notif-host` |
| `records/ros2/final-9ec4e836cb48/a2/` | 66 ROS 2 runs (11 scenarios × D/A × 3), each with `plan.json`, `manifest.json`, `logs/`, `judge.json`, `nc.json` (CT5 also `entries.json`); `summary.{json,md}`, `matrix.log`, `entries-CT5.log` |
| `records/core/final2-*`, `records/ros2/final-c6cef8724cd4/a1/` | Earlier version `cs-core-c6cef8724cd4` (kept, not counted) |
| `records/core/role-release-*`, `records/ros2/role-release-7ba114d5dcf9/a1/` | Earlier version `cs-core-7ba114d5dcf9` (kept, not counted) |
| `source/conditional-sharing/source-binding-check/` | Script, independent expectations and inputs of the separate source/binding static check (outside the snapshot members; `README.md` inside) |
| `env/` | `Dockerfile` of the image base, `ENVIRONMENT.md` (recorded versions of the current records `notif-host`, `notif-docker` and `final-9ec4e836cb48/a2`, QoS, unknowns; earlier versions kept at the end) |
| `traceability/CONTRACT-SPECIFICATION.md` | Self-contained specification of the independent evaluation contract (T1–T7 / `CT1`–`CT7`) |
| `traceability/EVIDENCE-INDEX.md` (+ `evidence-index.json`) | Scenario → input → expected → raw → verdict index: 16 core scenarios, 11 ROS 2 scenarios, 25 grammar cases, X1 30 rows × D/A, 24 negative controls, 4 contrasts, 12 sweep settings |
| `traceability/B3-CT5-multirole-trace.md` | Complete Manager/SafetyOfficer trace (B3) and the BipedMonitor/FleetMonitor core and ROS 2 counterpart with release of the last role (CT5), with assert / update / retract notifications |
| `traceability/C1-edit-example.md` | D / A / A-helper edits for the Wheeled threshold change 20 → 30 |
| `audit/` | Read-only re-judgment audits of the current evidence of record (`notif-core-rejudge-audit.json`, `notif-ros2-rejudge-audit.json`); earlier audits (`role-release-*`, `traceability-package-root-audit.json`, `ros2-rejudge-audit.json`) refer to the inputs of earlier versions |
| `MANIFEST.sha256` | SHA-256 of every file in this package except itself |

## Provenance and public cleanup notes

1. **Source snapshot (`cs-core-c6cef8724cd4` → `cs-core-8174f3ee50f2`):** The recorded runs in `records/core/final2-*/` and `records/ros2/final-c6cef8724cd4/` were executed against core snapshot `cs-core-c6cef8724cd4` (whose per-file SHA-256 manifest is preserved in `snapshots/cs-core-c6cef8724cd4.json`). For this public package, non-semantic authoring comments and internal path notes were cleaned in 23 non-code files (`inputs/expected/*.yml`, `inputs/expected/contract/*.yml`, `inputs/edit-units.yml`, `inputs/ontology/logistics-individuals.ttl`, `inputs/ontology/predicates/logistics-cs.ttl`, `runner/API.md`, `README.md`), and `expected-hashes.json` was updated accordingly to form `cs-core-8174f3ee50f2`. Every Python file (`.py`), scenario input (`inputs/scenarios/`), model file (`inputs/models/`), and parsed YAML data structure (`yaml.safe_load`) is 100% identical between `cs-core-c6cef8724cd4` and `cs-core-8174f3ee50f2`.
2. **Display-path sanitization in `records/`:** To remove local host and scratch directory paths without altering experimental data, the local workspace prefix (`<host-workspace>/paper-permission-infoflow`) was replaced with `<workspace>/paper-permission-infoflow` in `records/core/final2-host/{freeze-before.txt,freeze-after.txt,manifest.json}`, in the traceback strings of two negative-control logs (`records/core/final2-host/raw/negative/{T__D__no-validation.jsonl,X2__D__relation-only-check.jsonl}`), and in the recorded `docker run -v` command strings of `records/ros2/final-c6cef8724cd4/a1/*/manifest.json` (66 files); the temporary scratch prefix (`<host-temp>/scratchpad/snapx2`) was replaced with `<scratchpad>/snapx2` in `records/core/final2-docker/freeze-after-extracted.txt`. Because of this display-path sanitization, those 72 files are not byte-identical to the raw host files, whereas all 48 main core raw logs (`raw/main/*.jsonl`), all 60 X1 logs (`raw/x1/*.jsonl`), all 120 sweep logs, and all 66 ROS 2 process logs (`logs/*.jsonl`) are 100% byte-identical to the original recordings. The same replacement was applied to 14 files of the role-release records (`freeze-before.txt`, `freeze-after.txt` and `manifest.json` of `role-release-host`, the freeze files of `role-release-ct5-core`, the two negative-control logs named above in `role-release-host/raw/negative/`, `matrix.log` and the six run `manifest.json` files of `role-release-7ba114d5dcf9/a1`); their main raw logs, judge outputs and ROS 2 process logs are byte-identical to the recordings.
3. **CT5 revision (`cs-core-c6cef8724cd4` → `cs-core-7ba114d5dcf9` → public `cs-core-486f4f7b6ca3`):** The checker of the earlier version refused an agent with an empty role list, so CT5 had replaced the consumer's last role with `Idle`, a role without declarations, although contract T5 specifies `cfg2: []`. The revised version (1) accepts an empty role list as a valid assignment in `src/arms/d/checker.py` (the agent stays in the binding and acknowledgement set and has no reads or changes entries); (2) renames the CT5 roles `RoleA` → `BipedMonitor` and `RoleB` → `FleetMonitor` with unchanged conditions and releases the last role with `manager1: []` in the D, A and A-helper inputs; (3) adds the stored fact after every step to `inputs/expected/contract/CT5.yml`; (4) adds the consumer-entry table `inputs/expected/contract/CT5-entries.yml` with the checkers `tools/check_entries.py` (core) and `live/check_entries.py` (ROS 2 logs), and `live/scenario.sh` for repeated runs of selected scenarios. Other scenarios keep their `Idle` roles. A full core run under the revised version differs from `final2-host` only in the four CT5 raw files, with no verdict difference (`records/core/role-release-comparison.json`); the CT5 records replace, and are not added to, the earlier CT5 records. The public snapshot `cs-core-486f4f7b6ca3` differs from `cs-core-7ba114d5dcf9` in exactly the 25 files cleaned for `cs-core-8174f3ee50f2`; all Python files, scenario inputs and model files are identical and the cleaned YAML files parse to identical data. A core run from the public snapshot reproduces the CT5 raw files byte for byte.
4. **Knowledge notifications (`cs-core-7ba114d5dcf9` → `cs-core-9ec4e836cb48` → public `cs-core-a255c156de6c`):** The D Shared Memory core sends `assert` for the first supply of a fact (condition entry, re-entry, or a stored fact newly required after a configuration change), `update` for a new value of a supplied fact that still satisfies the condition, and `retract` for a condition exit, loss of the last supporting requirement, or deletion of a supplied fact; facts required under both configurations of a change receive no notification. A supplied fact is one whose previous stored value satisfied the consumer's condition. The A baseline keeps its LTM operations and rules; only its adapter to the application calls `on_assert`, `on_update` and `on_retract`. `commit`, acknowledgements and restart `sync` / `snapshot` messages remain control messages. The expected tables were converted by replaying the earlier independent expected calls in step order; scenarios, conditions, reported and stored values, views and decisions are unchanged. Negative-control labels became `no-retract` and `per-role-retract`; two judge-mutation controls and one raw-mutation control for notification kinds and unit checks N01–N13 (duplicates, retransmission, role release, restart resync) were added. Compared with the previous version, the 166 raw files differ only in notification kinds and in one intended-crash traceback, and no verdict differs (`records/core/notif-comparison.json`). Display paths of 71 files of the new records were sanitized as in note 2 (run manifests, the `notif-host` manifest and freeze files, two negative-control tracebacks). The public snapshot differs from the execution-time snapshot in exactly the 25 cleaned files; Python files, scenario and model inputs are identical, and a core run from the public snapshot reproduces all 48 main raw files byte for byte.
5. **Source/binding static check (added 2026-11-03):** `source/conditional-sharing/source-binding-check/` adds eight targeted cases for the checks that the 25 grammar cases do not exercise: a consumed context without a declared reporting role (`SOURCELESS`), a declared reporting role without a bound agent (`INCOMPLETE_BINDING`), a binding to an undefined role (`UNKNOWN_ROLE`), their corrected counterparts, a context with one of two reporting roles bound, and a revision refused before installation. Expectations were written before the first run. The script imports the frozen core read-only and lies outside the snapshot members, so `tools/snapshot.py verify cs-core-a255c156de6c` still passes and no source, input, expected table or record of the evidence of record changed. `records/core/source-binding-check/sb-9ec4-1` was run against `cs-core-9ec4e836cb48` (freeze verified before and after; 8/8; judge mutations 5/5 detected) and `pub-a255-1` against a copy of `source/conditional-sharing` (public snapshot verified; 8/8; observations identical). These cases are reported separately and are not added to the grammar cases, the 48 core runs or the 66 ROS 2 runs. Display paths were sanitized as in note 2 in four files (`sb-9ec4-1/verify-{before,after}.txt`, `pub-a255-1/manifest.json`, `pub-a255-1/verify-a255.txt`); `result.json` files are byte-identical to the recordings. The previous archive of this package is preserved outside the package. `env/ENVIRONMENT.md` now cites the current records; its earlier tables are kept unchanged at the end.

## Evidence boundaries

- Core results are in-process executions of the D path and of an ARBI-style Python reimplementation (A, A-helper); they are not runs of the original ARBI framework.
- ROS 2 results come from one host with Docker containers on a bridge network; they are not physical-robot, multi-host, or fault-recovery results.
- Edit counts are changed lines of versioned inputs, not human working time.
- Timing values are environment-bound exploration on a shared host.

## Commands

### 1. Package and snapshot integrity (no execution)

Run from the package root; every command stops with a non-zero exit on the first mismatch.

```bash
set -euo pipefail
shasum -a 256 -c MANIFEST.sha256 --quiet                       # every file of the package
cd snapshots
shasum -a 256 -c cs-core-a255c156de6c.tar.gz.sha256            # current public core archive
shasum -a 256 -c cs-core-486f4f7b6ca3.tar.gz.sha256            # earlier public core archives
shasum -a 256 -c cs-core-8174f3ee50f2.tar.gz.sha256
# The live .sha256 file names the archive by its original run path
# (live/runs/final-c6cef8724cd4/a1/live-snapshot.tar.gz), so compare the hash value explicitly:
want=$(cut -d' ' -f1 live-snapshot.tar.gz.sha256)
got=$(shasum -a 256 live-snapshot.tar.gz | cut -d' ' -f1)
[ "$want" = "$got" ] || { echo "live-snapshot.tar.gz: FAILED ($got != $want)"; exit 1; }
echo "live-snapshot.tar.gz: OK"
want=$(cut -d' ' -f1 live-snapshot-role-release.tar.gz.sha256)
got=$(shasum -a 256 live-snapshot-role-release.tar.gz | cut -d' ' -f1)
[ "$want" = "$got" ] || { echo "live-snapshot-role-release.tar.gz: FAILED ($got != $want)"; exit 1; }
echo "live-snapshot-role-release.tar.gz: OK"
want=$(cut -d' ' -f1 live-snapshot-notif.tar.gz.sha256)
got=$(shasum -a 256 live-snapshot-notif.tar.gz | cut -d' ' -f1)
[ "$want" = "$got" ] || { echo "live-snapshot-notif.tar.gz: FAILED ($got != $want)"; exit 1; }
echo "live-snapshot-notif.tar.gz: OK"
cd ../source/conditional-sharing
python3 tools/snapshot.py verify cs-core-a255c156de6c           # exit 1 and "DIFF [...]" on any difference
```

Expected live archive hashes: `10c87d7a76df7c31fb5ecb585b0f014b8724789e576320112687f9b745adc3ca` (`live-snapshot-notif.tar.gz`, current), `62c13aa3c7b5a3250a2b5004d37f4eb8364c7e805de61ae8c1ce53741b49df13` (`live-snapshot-role-release.tar.gz`) and `f8fbd738beb88c852baaa716356a239e27e04eaf42d7a13fbd25c101b9980cf3` (`live-snapshot.tar.gz`); the `.sha256` files name the archives by their original run paths.

### 2. Re-judge recorded raw files with the packaged judge (standard library + PyYAML)

```bash
cd source/conditional-sharing
python3 -m venv .venv && .venv/bin/pip install PyYAML==6.0.2
.venv/bin/python runner/judge.py ../../records/core/notif-host/raw/main/B3__D__main.jsonl inputs/expected/B3.yml inputs/scenarios/B3.yml
# records of an earlier version: extract that version's archive from snapshots/ and use its judge and inputs
```

### 3. Core rerun (writes `results/<run_id>/`, never overwrites `records/`)

```bash
cd source/conditional-sharing
./run.sh <new_run_id> .venv/bin/python cs-core-a255c156de6c
```

`run.sh` also calls `tools/regress_upstream_fixtures.py` on `../../../rcs-experiments` (override with `CS_RCS`); that external repository is not bundled, so the 88-fixture upstream regression is reported as `unavailable` unless `CS_RCS` points to a checkout of `rcs-experiments`. All other steps run self-contained.

### 4. ROS 2 rerun (requires Docker)

```bash
docker build -t rcs-experiments:jazzy env/          # FROM the pinned ros:jazzy digest
cd source/conditional-sharing
bash live/final.sh cs-core-a255c156de6c <new_attempt_label>
# CT5 only (D/A × 3, with the consumer-entry check):
# bash live/scenario.sh cs-core-a255c156de6c <label> <attempt> contract/CT5
# single run:
# python3 live/run.py --arm d --scenario contract/CT5 --expected contract/CT5 --rep 1 --label check --out-root <dir> --expect-snapshot cs-core-a255c156de6c
```

Prerequisite for `live/run.py` (unmodified from the frozen live runner): it records `git rev-parse HEAD` of the package root (two levels above `source/conditional-sharing`) and exits with an error if that directory is not inside a git working tree with at least one commit. When running from an extracted archive outside a git checkout, initialize a local repository at the package root first:

```bash
git init -q
git add -A
git -c user.name=local -c user.email=local@localhost commit -qm "local copy of the reproducibility package"
```

The `repo_head` field of new manifests will record that local commit rather than the original repository commit `6cf27105b43f37740a7449c662565e76f71e4621`. New runs write to `--out-root` / `live/runs/` and do not alter `records/`.

### 5. Source/binding static check (standard library + PyYAML, no ROS)

```bash
cd source/conditional-sharing
python3 tools/snapshot.py verify cs-core-a255c156de6c
.venv/bin/python -I source-binding-check/check_source_binding.py <new_run_id>   # exit 0 iff 8/8; writes source-binding-check/results/<new_run_id>/
```

## Recorded totals (checked against `records/`, version `cs-core-9ec4e836cb48`)

| Unit | Count | Source |
|---|---|---|
| Core main runs | 48/48 PASS (16 scenarios × D/A/A-helper), 1,326 judge rows, host and Docker identical verdicts | `records/core/notif-*/judgments.json`, `summary.json`, `audit/notif-core-rejudge-audit.json` |
| Grammar cases | 25/25 | `grammar.json` |
| Condition table X1 | 60/60 (30 rows × D/A); dup-branch NC fails 2 rows | `x1.json` |
| Negative controls | 24/24 failed as intended | `judgments.json` |
| Contrasts | 4/4 failed as intended | `judgments.json` |
| Judge-mutation controls | 23/23 as intended | `judge_nc.json` |
| Unit checks | 23/23 (U01–U10, N01–N13) | `check_units.json` |
| A static checks | 7/7 | `a_static.json` |
| CT5 consumer entries | core D/A/A-helper PASS; stale-model control 3/3 fails; ROS 2 6/6 | `records/core/notif-host/entries-CT5.json`, `records/core/notif-entries-nc/`, `records/ros2/final-9ec4e836cb48/a2/*/entries.json` |
| ROS 2 runs | 66/66 PASS, raw negative controls as intended 66/66 (10 mutations; 5 applicable to the zero-reception CT7-cfg0); notifications assert 126, update 18, retract 72 | `records/ros2/final-9ec4e836cb48/a2/summary.md`, `audit/notif-ros2-rejudge-audit.json` |
| Sweep | 12 settings × 5 reps × D/A = 120 rows, all correct | `sweep/sweep-summary.json`, `sweep-raw.jsonl` |
| Source/binding static check (separate, not counted above) | 8/8 (3 refusals, 4 acceptances, 1 refused revision); judge mutations 5/5 detected; public-snapshot rerun identical | `records/core/source-binding-check/` |
