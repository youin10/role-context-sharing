# Multi-role trace: B3 (Manager + SafetyOfficer) and CT5 (BipedMonitor + FleetMonitor)

Version: core snapshot `cs-core-9ec4e836cb48` (public source `cs-core-a255c156de6c`), consumer knowledge notifications assert / update / retract; core records `records/core/notif-host` (rerun `notif-docker`); ROS 2 records `records/ros2/final-9ec4e836cb48/a2` (CT5 only). Records of earlier versions are listed in `EVIDENCE-INDEX.md` Section 0 and are not counted.
All values below were read from the files cited; nothing was re-run except a read-only regeneration of the D configuration, whose `gen_sha256` equals the value recorded in the raw `start`/`change` records (see §1.3).

Evidence boundary: B3 was executed only in the in-process core harness (D, A, A-helper). It was **not** part of the eleven ROS 2 scenarios. The ROS 2 overlapping-role evidence is CT5, which uses the battery-monitoring roles BipedMonitor/FleetMonitor, not Manager/SafetyOfficer.

## 1. B3 — role combination, residual support 2 → 1 → 0 → 1

### 1.1 Inputs

| Item | File (under `source/conditional-sharing/`) |
|---|---|
| Scenario (steps, observer roster `[manager1]`) | `inputs/scenarios/B3.yml` |
| Expected table (independently specified) | `inputs/expected/B3.yml` |
| D declarations | `inputs/models/d/M1.org` (unchanged in all steps) |
| D bindings | `inputs/models/d/b-res2.yml` → `b-res1.yml` → `b-res0.yml` → `b-res1.yml` |
| A (explicit rules) | `inputs/models/a/initial-res.yml`, `plans/v1/{Manager,SafetyOfficer,Dispatcher}.yml`, `changes/R1.yml`, `R2.yml`, `R3.yml` |
| A-helper | `inputs/models/a-helper/config/v1.yml`, `assign/res2.yml`, `res1.yml`, `res0.yml`, `spec.yml` → generated `plans/v1/`, `changes/R1–R3.yml` |
| Ontology | `inputs/ontology/logistics-classes.ttl`, `logistics-individuals.ttl`, `predicates/logistics-cs.ttl` |

Declarations used for context RobotStatus (verbatim from `M1.org`; other roles and contexts in the file are listed in §1.4):

```text
role Manager {
  reads {
    logistics:RobotStatus($robot, $battery, $zone) {
      $robot == logistics:Biped && $battery <= 30 || $robot == logistics:Wheeled && $battery <= 20;
    }
    logistics:RobotStopped($robot, $elapsed) {
      $elapsed >= 300;
    }
  }
}
role Robot {
  changes {
    logistics:RobotStatus($robot, $battery, $zone);
    logistics:CargoCarriedBy($cargo, $robot);
  }
}
role SafetyOfficer {
  reads {
    logistics:RobotStatus($robot, $battery, $zone) {
      $battery <= 40;
    }
  }
}
role Dispatcher {
  reads {
    logistics:CargoCarriedBy($cargo, $robot);
  }
}
```

Bindings (`b-res2.yml`, initial): `manager1: [Manager, SafetyOfficer, Dispatcher]`, `biped1, humanoid1, wheeled1, diff1: [Robot]`, `cam1: [Observer]`.
`b-res1.yml`: `manager1: [Manager, Dispatcher]`. `b-res0.yml`: `manager1: [Dispatcher]`. Robot and Observer bindings are identical in all three files.

Ontology facts used (`predicates/logistics-cs.ttl`, `logistics-classes.ttl`, `logistics-individuals.ttl`):

- RobotStatus arguments: index 0 `robot` : `:Robot`, index 1 `battery` : `xsd:integer`, index 2 `zone` : `xsd:string`. The generated key of RobotStatus is `robot` (generated `keys.RobotStatus = "robot"`); battery and zone are the value fields.
- Classes: `Biped ⊑ Robot`, `Humanoid ⊑ Biped`, `Wheeled ⊑ Robot`, `DifferentialDrive ⊑ Wheeled`.
- Individuals: `biped1 : Biped`, `humanoid1 : Humanoid`, `wheeled1 : Wheeled`, `diff1 : DifferentialDrive`.
- RobotStopped's second argument is named `elapsedSeconds` in the ontology; `$elapsed` binds to it by position (raw condition field `elapsedSeconds`).

### 1.2 Steps (scenario file)

| Step | Input | Expected (independently specified, `inputs/expected/B3.yml`) |
|---|---|---|
| r01 | report by `biped1`: RobotStatus(biped1) = {battery: 25, zone: storage} | call `assert(RobotStatus, biped1, {25, storage})` |
| r02 | report by `wheeled1`: RobotStatus(wheeled1) = {battery: 35, zone: storage} | call `assert(RobotStatus, wheeled1, {35, storage})` |
| r03 | change R1: D binding `b-res1`; A `changes/R1` (SafetyOfficer removed) | call `retract(RobotStatus, wheeled1)`; view `{RobotStatus/biped1: {25, storage}}` |
| r04 | change R2: D binding `b-res0`; A `changes/R2` (Manager removed) | call `retract(RobotStatus, biped1)`; view `{}` |
| r05 | change R3: D binding `b-res1`; A `changes/R3` (Manager restored) | call `assert(RobotStatus, biped1, {25, storage})`; view `{RobotStatus/biped1: {25, storage}}` |

The expected table specifies calls for every step and views only for r03–r05. It has no `store` section; stored values in §1.3 are observations from the raw records and are not judged against an expectation.

### 1.3 Generated configuration (D) and observations (all arms)

D configuration per binding (raw `setup`/`change` records of `records/core/notif-host/raw/main/B3__D__main.jsonl`; reproduced read-only with `runner/api.py:d_generate`, identical `gen_sha256`):

| Binding | `gen_sha256` (prefix) | Producers of RobotStatus (`sources.RobotStatus.agents`) | Consumer entries for RobotStatus | Ψ(manager1, RobotStatus) as stored (DNF alternatives) | Other manager1 entries |
|---|---|---|---|---|---|
| b-res2 | `0de897ee…` | biped1, diff1, humanoid1, wheeled1 | manager1 | [robot isa Biped ∧ battery ≤ 30] ∨ [robot isa Wheeled ∧ battery ≤ 20] ∨ [battery ≤ 40] | CargoCarriedBy: [[]] (unconditional); RobotStopped: [elapsedSeconds ≥ 300] |
| b-res1 | `aa3f1896…` | same | manager1 | [robot isa Biped ∧ battery ≤ 30] ∨ [robot isa Wheeled ∧ battery ≤ 20] | CargoCarriedBy, RobotStopped as above |
| b-res0 | `2c4b0d83…` | same | none | — | CargoCarriedBy: [[]] only |

The generated `producers` map is identical in the three configurations: biped1, humanoid1, wheeled1, diff1 → {CargoCarriedBy, RobotStatus}; cam1 → {RobotStopped}; manager1 → none. No other agent is a consumer of RobotStatus in any configuration.

Observations (identical for D, A and A-helper; raw files `B3__D__main.jsonl`, `B3__A__main.jsonl`, `B3__A__helper.jsonl`):

| Step | manager1 roles | Support for biped1 (25) | Support for wheeled1 (35) | Observed call to manager1 | manager1 view after step | Shared Memory / LTM store after step |
|---|---|---|---|---|---|---|
| r01 | Manager, SafetyOfficer, Dispatcher | Manager (Biped ≤ 30), SafetyOfficer (≤ 40) | — | `assert(RobotStatus/biped1, battery=25, zone=storage)` | biped1: 25 | biped1: 25 |
| r02 | same | 2 | SafetyOfficer only (Wheeled ≤ 20 fails) | `assert(RobotStatus/wheeled1, battery=35, zone=storage)` | biped1: 25; wheeled1: 35 | biped1: 25; wheeled1: 35 |
| r03 | Manager, Dispatcher | 1 (Manager) | 0 | `retract(RobotStatus/wheeled1)`; no message for biped1 | biped1: 25 | unchanged |
| r04 | Dispatcher | 0 | 0 | `retract(RobotStatus/biped1)` | empty | unchanged |
| r05 | Manager, Dispatcher | 1 (Manager) | 0 | `assert(RobotStatus/biped1, battery=25, zone=storage)` (stored value; no new report) | biped1: 25 | unchanged |

Judge: 24 rows per arm, PASS for D, A and A-helper on host and in Docker (`judgments.json`, 5 expected positive calls). D statistics at end: `reports 2, assert 3, update 0, retract 2, rejected 0`. A end record: `ltm_counts {assert 2, match 9, notify 3}`; manager1 had 28 subscriptions over the run.

Configuration-change identifiers: D change records carry `seq` 1, 2, 3 (`change.seq`) and the commit messages carry `cfg` res1/res0/res1 with `change_id` R1/R2/R3. A change records carry `request_id` 1, 2, 3 acknowledged by manager1 with `cfg` R1/R2/R3; targets `[manager1]`. These wire-level markers are recorded but are not compared by the judge.

Report envelope identity (raw `input`): `event_id` `B3:r01`/`B3:r02`, `producer` biped1/wheeled1, `pv {n: 1, ts: 1|2}`, `op upsert`. The application view key is `<Context>/<instance>` (`RobotStatus/biped1`).

Negative control on the same expected table: `records/core/notif-host/raw/negative/B3__D__per-role-retract.jsonl` (retracts per removed role instead of on loss of all support). Observed: r03 `retract(biped1)` and `retract(wheeled1)`, view empty; r04 no call; judge FAIL with 3 failing rows, as intended.

### 1.4 Entries omitted from the RobotStatus projection

Entries that do not change during B3: all reporting entries (the `producers` map, including cam1 → RobotStopped and the robots' CargoCarriedBy entries) and manager1's Dispatcher entry (CargoCarriedBy, unconditional). Dispatcher stays bound to manager1 in all steps, so manager1 never has an empty role set.

Entry that does change but is outside the RobotStatus projection: manager1's RobotStopped consumer entry (condition `elapsedSeconds >= 300`) comes from Manager. It is present in res2 and res1, disappears at r04 (res0), and returns at r05 (res1). No RobotStopped report occurs in B3, so this change produces no call and no view entry.

M1.org also declares BipedTech, CarryAuditor and NonBipedWatch; they are unbound in the res bindings (generator warnings `UNUSED_ROLE`).

## 2. CT5 — overlapping role support and release of the last role (core and ROS 2)

Version: as in the header. CT5 releases the last role with an empty role list (introduced in `cs-core-7ba114d5dcf9`); its earlier records (`records/core/role-release-*`, `records/ros2/role-release-7ba114d5dcf9/a1`, and the RoleA/RoleB/`[Idle]` version in `records/core/final2-host`, `records/ros2/final-c6cef8724cd4/a1`) are kept and not counted (`EVIDENCE-INDEX.md` Section 0).

Inputs: `inputs/scenarios/contract/CT5.yml`, `inputs/expected/contract/CT5.yml`, `inputs/expected/contract/CT5-entries.yml`, `inputs/models/d/contract/CT5.org`, `b-ct5-0.yml` → `b-ct5-1.yml` → `b-ct5-2.yml`; A `inputs/models/a/contract/initial-ct5.yml`, `plans/ct5/{BipedMonitor,FleetMonitor}.yml`, `changes/CT5-1.yml`, `CT5-2.yml`; A-helper `inputs/models/a-helper/config/ct5.yml`, `assign/ct5-{0,1,2}.yml`.

```text
role BipedMonitor { reads { logistics:RobotStatus($robot, $battery, $zone) { $robot == logistics:Biped && $battery <= 30; } } }
role FleetMonitor { reads { logistics:RobotStatus($robot, $battery, $zone) { $robot == logistics:Robot && $battery <= 40; } } }
```

(Reformatted on one line each; the file uses the multi-line layout of §1.1.) Bindings: `manager1: [BipedMonitor, FleetMonitor]` → `[FleetMonitor]` → `[]` (no role; the agent stays in the binding and in the acknowledgement set); `biped1, hum1, wheel1: [Robot]`, `observer1: [Observer]`. BipedMonitor = RoleA and FleetMonitor = RoleB of the earlier version, with the same conditions.

| Step | Input | manager1 roles | Ψ(manager1, RobotStatus) | Expected | Observed core D / A / A-helper | Observed ROS 2 D r1–r3 / A r1–r3 |
|---|---|---|---|---|---|---|
| s1 | report biped1: {battery: 28, zone: storage} | BipedMonitor, FleetMonitor | (Biped ∧ ≤ 30) ∨ (Robot ∧ ≤ 40) | `assert(biped1, {28, storage})`; stored biped1: 28 | same, all three | same, 6/6 |
| c1 | change CT5-1 | FleetMonitor | Robot ∧ ≤ 40 | no call; view {biped1: 28}; stored biped1: 28 | same | same |
| c2 | change CT5-2 | none | no consumer entry | `retract(biped1)`; view {}; stored biped1: 28 | same | same |

Core: 22 judge rows per arm (including the stored fact after s1, c1 and c2), PASS on the host and in the Linux container. Consumer entries of manager1 (`records/core/notif-host/entries-CT5.json`): RobotStatus with two D alternatives at init, one at c1, and no entry at c2; for A and A-helper the LTM holds no subscription of manager1 after c2; manager1 remains in the active D agent set and acknowledged both A changes. The stale-model control (changes not applied) fails this entry check in all three approaches (`records/core/notif-entries-nc/entries-nc.json`). Negative control `raw/negative/CT5__D__per-role-retract.jsonl`: retract already at c1, FAIL with 3 rows as intended.
ROS 2: run directories `records/ros2/final-9ec4e836cb48/a2/final-{d,a}-contract_CT5-r{1,2,3}-*`; every `judge.json` PASS with 8 compared items (including the stored fact); raw negative controls `nc.json` all detected; `entries.json` PASS (D: the applied configuration of c2 has no RobotStatus entry for manager1 and the SM received manager1's ACK; A: the LTM subscription table rebuilt from its received messages holds no manager1 subscription after c2). Processes (D): `driver`, `d-sm`, `d-producer` (biped1, hum1, observer1, wheel1), `d-agent-manager1`. The observed call record in `logs/d-agent-manager1.jsonl` names its cause message (topic `/d/inbox/manager1`, rx sequence and payload hash), e.g. `deliver` at s1 with `e: CT5:s1`, `revoke` at c2 with `n: 1-manager1-3`.

## 3. Suggested symbolic notation for the paper and its mapping to the trace

| Symbol | Meaning | Trace identifier |
|---|---|---|
| $c$ | RobotStatus | `RobotStatus` (key argument `robot`, values `battery`, `zone`) |
| $m$ | coordinator agent | `manager1` |
| $b, h, w, d$ | reporting robots | `biped1` (Biped), `humanoid1` (Humanoid ⊑ Biped), `wheeled1` (Wheeled), `diff1` (DifferentialDrive ⊑ Wheeled) |
| $P$ | producers of $c$ | generated `sources.RobotStatus.agents` = {biped1, diff1, humanoid1, wheeled1} |
| $S_p^c$ | reporting entries for $c$ | `producers[a]` contains `RobotStatus` for each $a\in P$ |
| $S_c^c$ | consumer entries for $c$ | agents with a `consumers[a].RobotStatus` entry: {manager1} in res2/res1, ∅ in res0 |
| $\varphi_M$ | Manager's RobotStatus condition | DNF alternatives 1–2 in the raw `consumers.manager1.RobotStatus` |
| $\varphi_S$ | SafetyOfficer's condition | DNF alternative 3 (`battery <= 40`) |
| $\Psi_{m,c}$ | combined condition | full `consumers.manager1.RobotStatus` list (OR of alternatives) |
| supply / withdraw | consumer knowledge notifications | `assert` (first supply, including a stored value after a configuration change), `update` (new value of a supplied fact) / `retract` |

Exact example sentences supported by the records:

- "With Manager and SafetyOfficer bound to $m$, $\Psi_{m,c}=\varphi_M\lor\varphi_S$; reports $b$: 25% and $w$: 35% were both supplied to $m$." (r01, r02)
- "Removing SafetyOfficer withdrew $w$ only; $b$ remained in $m$'s view without a message, because Manager still required it." (r03)
- "Removing Manager withdrew $b$; both values remained stored." (r04)
- "Restoring Manager supplied the stored value of $b$ (25%) without a new report; $w$ (35%) was not supplied because Manager's wheeled threshold is 20%." (r05)
