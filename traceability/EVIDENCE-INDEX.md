# Evidence index — conditional-sharing (snapshot cs-core-9ec4e836cb48)

All paths are relative to this package root. Core = in-process run `notif-host` (rerun in a Linux container `notif-docker`, same verdicts). ROS 2 = `records/ros2/final-9ec4e836cb48/a2` (single host, Docker, D and A only, 3 repetitions). Both use snapshot `cs-core-9ec4e836cb48` (public source `cs-core-a255c156de6c`), in which consumers receive the knowledge notifications assert / update / retract (Section 0). Expected tables were written independently of implementation output and are frozen by `expected-hashes.json`. Machine-readable version: `evidence-index.json`.

## 0. Versions and evidence lineage

Consumer knowledge notifications: `assert` adds a fact to the consumer's local knowledge (first supply: condition entry, re-entry, or a stored fact newly required after a configuration change), `update` revises the value of a fact already supplied that still satisfies the condition, and `retract` removes a supplied fact (condition exit, loss of the last supporting requirement, or source deletion). Shared Memory decides the kind; a retract after a condition exit or a requirement change does not delete the stored fact. Earlier versions recorded `deliver` (entry and update, or deletion with a null value), `current` (supply after a configuration change) and `revoke` (exit or loss). The expected tables were converted by replaying the earlier independent expected calls in step order (deliver/current → assert for a fact not yet supplied, deliver → update for a supplied fact, revoke/delete → retract). Scenarios, conditions, reported values, stored values, views and decisions are unchanged.

| Version | Change | Core records | ROS 2 records | Counted |
|---|---|---|---|---|
| `cs-core-9ec4e836cb48` (public `cs-core-a255c156de6c`) | knowledge notifications assert / update / retract | `records/core/notif-host`, `records/core/notif-docker` | `records/ros2/final-9ec4e836cb48/a2` | yes: 48 core runs (1,326 judge rows), 66 ROS 2 runs |
| `cs-core-7ba114d5dcf9` (public `cs-core-486f4f7b6ca3`) | CT5 releases the last role with an empty role list | `records/core/role-release-host`, `role-release-docker`, `role-release-ct5-core` | `records/ros2/role-release-7ba114d5dcf9/a1` (CT5) | no |
| `cs-core-c6cef8724cd4` (public `cs-core-8174f3ee50f2`) | original evaluation version | `records/core/final2-host`, `final2-docker` | `records/ros2/final-c6cef8724cd4/a1` | no |

Comparison with the previous version: `records/core/notif-comparison.json` (all 166 raw files of `role-release-host` and `notif-host`): the only differences are the notification kinds of 609 calls (deliver → assert 324, deliver → update 160, current → assert 13, delete → retract 53, revoke → retract 59) and the traceback text of one intended-crash negative control; no verdict differs. Records of earlier versions are re-judged with the judge and inputs extracted from their own public snapshot archive in `snapshots/`, never with the current inputs.

## 1. Sixteen core scenarios (D / A / A-helper = 48 runs) and the eleven ROS 2 scenarios

| Scenario | What it checks (scenario title) | D input (model / binding) | A input | Expected | Judge rows per arm | Host / Docker verdict | ROS 2 runs (D, A) |
|---|---|---|---|---|---|---|---|
| B1 | same model, data changes (entry / update / exit / deletion), typed OR condition, subclasses | `{model: M1, binding: b-main}` | `{initial: initial-main-v1}` | `source/conditional-sharing/inputs/expected/B1.yml` | 50/50/50 | PP/PP/PP | — |
| T | unknown individual, wrongly typed individual, ill-typed value, missing field | `{model: M1, binding: b-main}` | `{initial: initial-main-v1}` | `source/conditional-sharing/inputs/expected/T.yml` | 35/35/35 | PP/PP/PP | 3/3, 3/3 PASS |
| B2 | model change at fixed data (Wheeled threshold <=20 -> <=30 -> <=20), no new report | `{model: M1, binding: b-main}` | `{initial: initial-main-v1}` | `source/conditional-sharing/inputs/expected/B2.yml` | 22/22/22 | PP/PP/PP | — |
| B3 | role combination, residual support 2 -> 1 -> 0 -> 1 | `{model: M1, binding: b-res2}` | `{initial: initial-res}` | `source/conditional-sharing/inputs/expected/B3.yml` | 24/24/24 | PP/PP/PP | — |
| K | individual-constant key condition, class negation, entity-valued non-key field | `{model: M1, binding: b-main}` | `{initial: initial-main-v1}` | `source/conditional-sharing/inputs/expected/K.yml` | 51/51/51 | PP/PP/PP | 3/3, 3/3 PASS |
| S1 | RobotStopped(robot, elapsedSeconds) produced by the observer, threshold 300 s (provisional) | `{model: M1, binding: b-main}` | `{initial: initial-main-v1}` | `source/conditional-sharing/inputs/expected/S1.yml` | 25/25/25 | PP/PP/PP | — |
| P1 | fixed plan validation - independent decision schedule over one event trace and one model change | `{model: M1, binding: b-main}` | `{initial: initial-main-v1}` | `source/conditional-sharing/inputs/expected/P1.yml` | 38/38/38 | PP/PP/PP | 3/3, 3/3 PASS |
| X2 | class compatibility beyond the subclass relation - signature Biped, condition == Wheeled (hybrid1) | `{model: X2, binding: b-x2}` | `{initial: initial-x2}` | `source/conditional-sharing/inputs/expected/X2.yml` | 23/23/23 | PP/PP/PP | — |
| CT1 | contract T1 battery boundary, type and subtype | `{model: contract/CT-typed, binding: contract/b-ct}` | `{initial: contract/initial-typed}` | `source/conditional-sharing/inputs/expected/contract/CT1.yml` | 24/24/24 | PP/PP/PP | 3/3, 3/3 PASS |
| CT2 | contract T2 individual ID constant on the first argument | `{model: contract/CT2, binding: contract/b-ct}` | `{initial: contract/initial-ct2}` | `source/conditional-sharing/inputs/expected/contract/CT2.yml` | 18/18/18 | PP/PP/PP | 3/3, 3/3 PASS |
| CT3 | contract T3 entry / stay / exit vs deletion | `{model: contract/CT-typed, binding: contract/b-ct}` | `{initial: contract/initial-typed}` | `source/conditional-sharing/inputs/expected/contract/CT3.yml` | 28/28/28 | PP/PP/PP | 3/3, 3/3 PASS |
| CT4 | contract T4 model redeployment snapshot, no new reports | `{model: contract/CT4-0, binding: contract/b-ct}` | `{initial: contract/initial-ct4-0}` | `source/conditional-sharing/inputs/expected/contract/CT4.yml` | 21/21/21 | PP/PP/PP | 3/3, 3/3 PASS |
| CT5 | contract T5 overlapping role support: BipedMonitor + FleetMonitor -> FleetMonitor -> no role | `{model: contract/CT5, binding: contract/b-ct5-0}` | `{initial: contract/initial-ct5}` | `source/conditional-sharing/inputs/expected/contract/CT5.yml` | 22/22/22 | PP/PP/PP | 3/3, 3/3 PASS |
| CT6 | contract T6 RobotStopped elapsed time | `{model: contract/CT-typed, binding: contract/b-ct}` | `{initial: contract/initial-typed}` | `source/conditional-sharing/inputs/expected/contract/CT6.yml` | 22/22/22 | PP/PP/PP | 3/3, 3/3 PASS |
| CT7-cfg1 | contract T7 fixed decision schedule outside the model (cfg1) | `{model: contract/CT-typed, binding: contract/b-ct}` | `{initial: contract/initial-typed}` | `source/conditional-sharing/inputs/expected/contract/CT7-cfg1.yml` | 20/20/20 | PP/PP/PP | 3/3, 3/3 PASS |
| CT7-cfg0 | contract T7 fixed decision schedule outside the model (cfg0) | `{model: contract/CT7-0, binding: contract/b-ct}` | `{initial: contract/initial-ct7-0}` | `source/conditional-sharing/inputs/expected/contract/CT7-cfg0.yml` | 19/19/19 | PP/PP/PP | 3/3, 3/3 PASS |

Raw core records: `records/core/notif-host/raw/main/<scenario>__<D|A>__<main|helper>.jsonl`. Verdicts: `records/core/notif-host/judgments.json`. Judge rows are D/A/A-helper; verdict pairs are host+docker (P = pass). ROS 2 run directories: `records/ros2/final-9ec4e836cb48/a2/final-<d|a>-<scenario>-r<1..3>-<stamp>/` with `plan.json`, `manifest.json`, `logs/<process>.jsonl`, `judge.json`. B1, B2, B3, S1 and X2 were not executed through ROS 2.

## 2. Declaration checks (25 grammar cases)

Input text, expected DNF or error code, and the observed result are inside `records/core/notif-host/grammar.json` (one object per case). Expected source: `source/conditional-sharing/inputs/expected/G-grammar.yml`.

Purpose notes are copied from `grammar.json`; where the expected table records no note, the cell says so. The predicate and condition block are the actual case input from `G-grammar.yml`.

| Case | Purpose note (as recorded) | Predicate | Condition block (case input) | Expected | Observed codes / stage | Judge verdict |
|---|---|---|---|---|---|---|
| G01 | typed OR in one line, && binds tighter than \|\| | RobotStatus | `$robot == logistics:Biped && $battery <= 30 \|\| $robot == logistics:Wheeled && $battery <= 20;` | accepted; DNF with 2 alternative(s) | [] / generated | PASS |
| G02 | two lines are a conjunction | RobotStatus | `$robot == logistics:Biped; $battery <= 30;` | accepted; DNF with 1 alternative(s) | [] / generated | PASS |
| G03 | lines distribute over an OR line (DNF) | RobotStatus | `$robot == logistics:Biped \|\| $robot == logistics:Wheeled; $battery <= 20;` | accepted; DNF with 2 alternative(s) | [] / generated | PASS |
| G04 | AND-only alternative - the same predicate twice in one role is refused, so OR is needed in one role | RobotStatus | `(full model case; see grammar.json text)` | DUPLICATE_READ | ['DUPLICATE_READ'] / parsed | PASS |
| G05 | identity of the first argument (individual ID) | RobotStatus | `$robot == "biped1";` | accepted; DNF with 1 alternative(s) | [] / generated | PASS |
| G06 | a quoted class name is an ID, not a class | RobotStatus | `$robot == "Biped";` | UNKNOWN_INDIVIDUAL | ['UNKNOWN_INDIVIDUAL'] / parsed | PASS |
| G07 | (no note recorded) | RobotStatus | `$robot == logistics:Bipedal;` | UNKNOWN_CLASS | ['UNKNOWN_CLASS'] / parsed | PASS |
| G08 | class unrelated to argumentType Robot | RobotStatus | `$robot == logistics:Cargo;` | TYPE_MISMATCH | ['TYPE_MISMATCH'] / parsed | PASS |
| G09 | numeric comparison on an ID | RobotStatus | `$robot < 3;` | TYPE_MISMATCH | ['TYPE_MISMATCH'] / parsed | PASS |
| G10 | ordered operator with a class | RobotStatus | `$robot <= logistics:Biped;` | TYPE_MISMATCH | ['TYPE_MISMATCH'] / None | PASS |
| G11 | class condition on a literal (integer) argument | RobotStatus | `$battery == logistics:Biped;` | TYPE_MISMATCH | ['TYPE_MISMATCH'] / parsed | PASS |
| G12 | registered individual of the wrong class | RobotStatus | `$robot == "cargo1";` | TYPE_MISMATCH | ['TYPE_MISMATCH'] / parsed | PASS |
| G13 | (no note recorded) | RobotStatus | `$robot != logistics:Biped;` | accepted; DNF with 1 alternative(s) | [] / generated | PASS |
| G14 | (no note recorded) | RobotStatus | `$zone == "storage";` | accepted; DNF with 1 alternative(s) | [] / generated | PASS |
| G15 | entity-valued non-key argument | CargoCarriedBy | `$robot == logistics:Biped;` | accepted; DNF with 1 alternative(s) | [] / generated | PASS |
| G16 | (no note recorded) | CargoCarriedBy | `$robot == "ghost9";` | UNKNOWN_INDIVIDUAL | ['UNKNOWN_INDIVIDUAL'] / parsed | PASS |
| G17 | (no note recorded) | RobotStatus | `$nothere == 1;` | UNKNOWN_FIELD | ['UNKNOWN_FIELD'] / None | PASS |
| G18 | (no note recorded) | RobotStatus | `$robot == nope:Biped;` | UNDECLARED_PREFIX | ['UNDECLARED_PREFIX'] / None | PASS |
| G19 | (no note recorded) | RobotStatus | `$battery <= 30 && $battery > 30;` | UNSATISFIABLE | ['UNSATISFIABLE'] / parsed | PASS |
| G20 | no parenthesised expressions | RobotStatus | `($battery <= 30);` | SYNTAX | ['SYNTAX'] / None | PASS |
| G21 | numeric comparison on a non-key ID argument | CargoCarriedBy | `$robot >= 1;` | TYPE_MISMATCH | ['TYPE_MISMATCH'] / parsed | PASS |
| G22 | signature Biped, condition Wheeled - valid because hybrid1 is both | BipedBalance | `$robot == logistics:Wheeled;` | accepted; DNF with 1 alternative(s) | [] / generated | PASS |
| G23 | no subclass and no individual is both Biped and Cargo | BipedBalance | `$robot == logistics:Cargo;` | TYPE_MISMATCH | ['TYPE_MISMATCH'] / parsed | PASS |
| G24 | no subclass and no individual is both Biped and DifferentialDrive (diff1 is not Biped) | BipedBalance | `$robot == logistics:DifferentialDrive;` | TYPE_MISMATCH | ['TYPE_MISMATCH'] / parsed | PASS |
| G25 | (no note recorded) | BipedBalance | `$robot != logistics:Wheeled;` | accepted; DNF with 1 alternative(s) | [] / generated | PASS |

## 3. Condition truth table X1 (30 rows × D/A = 60 runs)

Rows: robot × battery value; expected truth from `source/conditional-sharing/inputs/expected/X1-truth.yml`; verdicts in `records/core/notif-host/x1.json`; raw in `records/core/notif-host/raw/x1/`. The `dup-branch` negative control runs on the same 30 rows and must fail only where both branches hold (hybrid1 at 19 and 20).

Verdict columns state whether the observation matched the expected supply (PASS/FAIL); they do not mean supply. Observed supply (assert calls) is shown separately.

| Robot | Battery | Expected supply | D observed supply | D verdict | A observed supply | A verdict | dup-branch NC verdict |
|---|---|---|---|---|---|---|---|
| biped1 | 19 | yes | yes (1 call) | PASS | yes (1 call) | PASS | PASS |
| biped1 | 20 | yes | yes (1 call) | PASS | yes (1 call) | PASS | PASS |
| biped1 | 21 | yes | yes (1 call) | PASS | yes (1 call) | PASS | PASS |
| biped1 | 29 | yes | yes (1 call) | PASS | yes (1 call) | PASS | PASS |
| biped1 | 30 | yes | yes (1 call) | PASS | yes (1 call) | PASS | PASS |
| biped1 | 31 | no | no | PASS | no | PASS | PASS |
| humanoid1 | 19 | yes | yes (1 call) | PASS | yes (1 call) | PASS | PASS |
| humanoid1 | 20 | yes | yes (1 call) | PASS | yes (1 call) | PASS | PASS |
| humanoid1 | 21 | yes | yes (1 call) | PASS | yes (1 call) | PASS | PASS |
| humanoid1 | 29 | yes | yes (1 call) | PASS | yes (1 call) | PASS | PASS |
| humanoid1 | 30 | yes | yes (1 call) | PASS | yes (1 call) | PASS | PASS |
| humanoid1 | 31 | no | no | PASS | no | PASS | PASS |
| wheeled1 | 19 | yes | yes (1 call) | PASS | yes (1 call) | PASS | PASS |
| wheeled1 | 20 | yes | yes (1 call) | PASS | yes (1 call) | PASS | PASS |
| wheeled1 | 21 | no | no | PASS | no | PASS | PASS |
| wheeled1 | 29 | no | no | PASS | no | PASS | PASS |
| wheeled1 | 30 | no | no | PASS | no | PASS | PASS |
| wheeled1 | 31 | no | no | PASS | no | PASS | PASS |
| diff1 | 19 | yes | yes (1 call) | PASS | yes (1 call) | PASS | PASS |
| diff1 | 20 | yes | yes (1 call) | PASS | yes (1 call) | PASS | PASS |
| diff1 | 21 | no | no | PASS | no | PASS | PASS |
| diff1 | 29 | no | no | PASS | no | PASS | PASS |
| diff1 | 30 | no | no | PASS | no | PASS | PASS |
| diff1 | 31 | no | no | PASS | no | PASS | PASS |
| hybrid1 | 19 | yes | yes (1 call) | PASS | yes (1 call) | PASS | FAIL as intended (observed 2 calls) |
| hybrid1 | 20 | yes | yes (1 call) | PASS | yes (1 call) | PASS | FAIL as intended (observed 2 calls) |
| hybrid1 | 21 | yes | yes (1 call) | PASS | yes (1 call) | PASS | PASS |
| hybrid1 | 29 | yes | yes (1 call) | PASS | yes (1 call) | PASS | PASS |
| hybrid1 | 30 | yes | yes (1 call) | PASS | yes (1 call) | PASS | PASS |
| hybrid1 | 31 | no | no | PASS | no | PASS | PASS |

## 4. Negative controls (24) and contrasts (4)

Each control runs a deliberately broken variant against the unchanged expected table; the intended result is a judge FAIL. The variant table is in `source/conditional-sharing/runner/run_all.py`: some variants alter processing (`source/conditional-sharing/runner/variants.py`), others substitute inputs (e.g. `inputs/models/d/M1-strict.org`, `inputs/models/d/nc/*`, `inputs/models/a/initial-main-strict.yml`).

| Kind | Scenario | Arm | Variant | Fault introduced | Failing judge rows | Failed as intended | Raw |
|---|---|---|---|---|---|---|---|
| negative | B1 | D | boundary-lt | boundary error (< instead of <=) | 10 | yes | `records/core/notif-host/raw/negative/B1__D__boundary-lt.jsonl` |
| negative | B1 | A | boundary-lt | boundary error (< instead of <=) | 10 | yes | `records/core/notif-host/raw/negative/B1__A__boundary-lt.jsonl` |
| negative | CT1 | D | boundary-lt | boundary error (< instead of <=) | 5 | yes | `records/core/notif-host/raw/negative/CT1__D__boundary-lt.jsonl` |
| negative | B1 | D | no-retract | retract omission | 8 | yes | `records/core/notif-host/raw/negative/B1__D__no-retract.jsonl` |
| negative | CT3 | D | no-retract | retract omission | 2 | yes | `records/core/notif-host/raw/negative/CT3__D__no-retract.jsonl` |
| negative | B1 | A | asis | retract omission (A-asis: no exit watch, no tombstones) | 10 | yes | `records/core/notif-host/raw/negative/B1__A__asis.jsonl` |
| negative | CT3 | A | asis | retract omission (A-asis: no exit watch, no tombstones) | 5 | yes | `records/core/notif-host/raw/negative/CT3__A__asis.jsonl` |
| negative | B1 | D | signature-as-type | wrong-type reception | 11 | yes | `records/core/notif-host/raw/negative/B1__D__signature-as-type.jsonl` |
| negative | CT1 | D | signature-as-type | wrong-type reception | 2 | yes | `records/core/notif-host/raw/negative/CT1__D__signature-as-type.jsonl` |
| negative | B1 | D | non-transitive | subclass missing | 6 | yes | `records/core/notif-host/raw/negative/B1__D__non-transitive.jsonl` |
| negative | CT1 | D | non-transitive | subclass missing | 3 | yes | `records/core/notif-host/raw/negative/CT1__D__non-transitive.jsonl` |
| negative | B3 | D | per-role-retract | residual-support mistake | 3 | yes | `records/core/notif-host/raw/negative/B3__D__per-role-retract.jsonl` |
| negative | CT5 | D | per-role-retract | residual-support mistake | 3 | yes | `records/core/notif-host/raw/negative/CT5__D__per-role-retract.jsonl` |
| negative | B2 | D | stale-model | model not updated | 3 | yes | `records/core/notif-host/raw/negative/B2__D__stale-model.jsonl` |
| negative | B2 | A | stale-model | plan not updated | 3 | yes | `records/core/notif-host/raw/negative/B2__A__stale-model.jsonl` |
| negative | CT4 | D | stale-model | model not updated | 3 | yes | `records/core/notif-host/raw/negative/CT4__D__stale-model.jsonl` |
| negative | CT4 | A | stale-model | plan not updated | 3 | yes | `records/core/notif-host/raw/negative/CT4__A__stale-model.jsonl` |
| negative | S1 | D | stop-299 | RobotStopped early entry at 299 s | 4 | yes | `records/core/notif-host/raw/negative/S1__D__stop-299.jsonl` |
| negative | CT6 | D | stop-299 | RobotStopped early entry at 299 s | 2 | yes | `records/core/notif-host/raw/negative/CT6__D__stop-299.jsonl` |
| negative | T | D | no-validation | unknown / ill-typed values not detected (crashes on the unregistered individual) | 7 | yes | `records/core/notif-host/raw/negative/T__D__no-validation.jsonl` |
| negative | T | A | no-guard | unknown / ill-typed values not detected (A without the catalogue helper) | 9 | yes | `records/core/notif-host/raw/negative/T__A__no-guard.jsonl` |
| negative | X2 | D | relation-only-check | class compatibility limited to the subclass relation (refuses a valid Biped/Wheeled condition) | 9 | yes | `records/core/notif-host/raw/negative/X2__D__relation-only-check.jsonl` |
| negative | B1 | A | helper-boundary-lt | helper A with a boundary error (< instead of <=) | 10 | yes | `records/core/notif-host/raw/negative/B1__A__helper-boundary-lt.jsonl` |
| negative | B2 | A | helper-stale-model | helper A plan not updated | 3 | yes | `records/core/notif-host/raw/negative/B2__A__helper-stale-model.jsonl` |
| contrast | P1 | D | noupdate | fixed plan without the model update | 4 | yes | `records/core/notif-host/raw/contrast/P1__D__noupdate.jsonl` |
| contrast | P1 | D | nocond | fixed plan without data conditions | 14 | yes | `records/core/notif-host/raw/contrast/P1__D__nocond.jsonl` |
| contrast | P1 | A | noupdate | fixed plan without the plan update | 4 | yes | `records/core/notif-host/raw/contrast/P1__A__noupdate.jsonl` |
| contrast | P1 | A | nocond | fixed plan with unconditional rules | 14 | yes | `records/core/notif-host/raw/contrast/P1__A__nocond.jsonl` |

Judge-mutation controls (23, including two notification-kind misclassifications) for the core judge: `records/core/notif-host/judge_nc.json`; raw-mutation controls for the ROS 2 judge: `nc.json` in each ROS 2 run directory.

## 5. Scale sweep (12 settings × 5 repetitions × D/A = 120 raw rows)

Workload per setting: 4 rounds × R reports + one redeployment (Wheeled +10). Expected calls come from a closed form in `source/conditional-sharing/tools/sweep.py` that does not import the implementation. Raw: `records/core/notif-host/sweep/sweep-raw.jsonl`; medians: `records/core/notif-host/sweep/sweep-summary.json`.

| Setting | R (individuals) | M (consumers) | C (conditional roles/consumer) | Expected calls/consumer | D correct (5/5) | A correct (5/5) | Generated inputs |
|---|---|---|---|---|---|---|---|
| R1-M4-C4 | 1 | 4 | 4 | 3 | yes | yes | `records/core/notif-host/sweep/inputs/R1-M4-C4/` |
| R4-M4-C4 | 4 | 4 | 4 | 14 | yes | yes | `records/core/notif-host/sweep/inputs/R4-M4-C4/` |
| R16-M4-C4 | 16 | 4 | 4 | 56 | yes | yes | `records/core/notif-host/sweep/inputs/R16-M4-C4/` |
| R64-M4-C4 | 64 | 4 | 4 | 224 | yes | yes | `records/core/notif-host/sweep/inputs/R64-M4-C4/` |
| R4-M1-C4 | 4 | 1 | 4 | 14 | yes | yes | `records/core/notif-host/sweep/inputs/R4-M1-C4/` |
| R4-M16-C4 | 4 | 16 | 4 | 14 | yes | yes | `records/core/notif-host/sweep/inputs/R4-M16-C4/` |
| R4-M64-C4 | 4 | 64 | 4 | 14 | yes | yes | `records/core/notif-host/sweep/inputs/R4-M64-C4/` |
| R4-M4-C1 | 4 | 4 | 1 | 14 | yes | yes | `records/core/notif-host/sweep/inputs/R4-M4-C1/` |
| R4-M4-C16 | 4 | 4 | 16 | 14 | yes | yes | `records/core/notif-host/sweep/inputs/R4-M4-C16/` |
| R4-M4-C64 | 4 | 4 | 64 | 14 | yes | yes | `records/core/notif-host/sweep/inputs/R4-M4-C64/` |
| R1-M1-C1 | 1 | 1 | 1 | 3 | yes | yes | `records/core/notif-host/sweep/inputs/R1-M1-C1/` |
| R16-M16-C16 | 16 | 16 | 16 | 56 | yes | yes | `records/core/notif-host/sweep/inputs/R16-M16-C16/` |

Note: the sweep variable names R/M/C in the files correspond to the manuscript's N/K/Q.

## 6. Path validation

Every path written into this index and `evidence-index.json` was checked for existence when the index was generated: 210 paths, 0 missing.

## 7. Source/binding static check (separate; 8 cases)

Added 2026-11-03. These cases exercise the pre-generation checks that the 25 grammar cases do not cover. They are reported separately and are not counted in Sections 1–5. Expectations (`source/conditional-sharing/source-binding-check/expected.yml`) were written before the first run; the script imports the frozen core read-only and is outside the snapshot members. Record of the execution-time snapshot `cs-core-9ec4e836cb48`: `records/core/source-binding-check/sb-9ec4-1/` (`result.json`, `manifest.json`, `verify-before.txt`, `verify-after.txt`, `judge-mutations.json`: 5/5 mutations detected). Rerun on the public snapshot: `records/core/source-binding-check/pub-a255-1/` (observations identical, `comparison-with-sb-9ec4-1.json`).

| Case | Purpose (from the expected table) | Input | Expected | Observed (sb-9ec4-1) | Verdict 9ec4 | Verdict a255 |
|---|---|---|---|---|---|---|
| SB1 | consumer reads a context that no role declares in changes (missing source declaration) | `source/conditional-sharing/source-binding-check/inputs/sourceless.org` + `b-full.yml` | refused, SOURCELESS | refused: SOURCELESS roles.Manager.reads.RobotStopped | PASS | PASS |
| SB1-P | paired valid input - Observer declares changes RobotStopped and is bound | `source/conditional-sharing/source-binding-check/inputs/sourceless-paired.org` + `b-sourceless-paired.yml` | accepted with expected entries | generated; consumers {"manager1": ["RobotStatus", "RobotStopped"]} | PASS | PASS |
| SB2 | declared but unbound source (R1-1 counterexample) - Robot declares changes, only Manager bound | `source/conditional-sharing/source-binding-check/inputs/base.org` + `b-consumer-only.yml` | refused, INCOMPLETE_BINDING | refused: INCOMPLETE_BINDING roles.Manager.reads.RobotStatus; warning UNUSED_ROLE | PASS | PASS |
| SB2-P | paired valid input - same model, Robot bound to biped1 | `source/conditional-sharing/source-binding-check/inputs/base.org` + `b-full.yml` | accepted with expected entries | generated; consumers {"manager1": ["RobotStatus"]} | PASS | PASS |
| SB3 | binding names a role that the model does not define | `source/conditional-sharing/source-binding-check/inputs/base.org` + `b-unknown-role.yml` | refused, UNKNOWN_ROLE | refused: UNKNOWN_ROLE binding.insp1 | PASS | PASS |
| SB3-P | paired valid input - the unknown binding removed (same as SB2-P) | `source/conditional-sharing/source-binding-check/inputs/base.org` + `b-full.yml` | accepted with expected entries | generated; consumers {"manager1": ["RobotStatus"]} | PASS | PASS |
| SB4 | boundary - two declared source roles, only one bound; one bound source suffices | `source/conditional-sharing/source-binding-check/inputs/two-sources.org` + `b-auditor-only.yml` | accepted with expected entries | generated; consumers {"manager1": ["RobotStatus"]}; warning UNUSED_ROLE | PASS | PASS |
| SB5 | revision refused before installation - active valid configuration (SB2-P) is kept when the revised input is SB2 (declared-but-unbound source) | initial `source/conditional-sharing/source-binding-check/inputs/base.org` + `b-full.yml`; revised binding `b-consumer-only.yml` | revision refused; active configuration unchanged | refused (INCOMPLETE_BINDING); active seq 0, cfg b-full, messages 0 | PASS | PASS |

Paths written in this section were checked for existence when it was added: 22 paths, 0 missing.
