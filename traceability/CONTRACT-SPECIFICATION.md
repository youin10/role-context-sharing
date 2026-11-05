# Independent Contract Specification (CT1–CT7)

This document defines the implementation-independent expected reception and fixed-plan decision contract (`CT1`–`CT7`) used by `source/conditional-sharing/inputs/expected/contract/*.yml`. All expected traces are derived strictly from the domain policy and set-theoretic semantics before running any generator (`generator.py`), runtime (`smcore.py`), or parser.

---

## 1. Scope and Semantic Rules

- **Pipeline:** EBNF permission specification model $\to$ sharing configuration derivation and redeployment $\to$ selective context provision $\to$ fixed-plan decision consumption.
- **First-argument (key) conditions and class hierarchy:** Conditions may constrain any predicate argument, including the first (instance-key) argument. A class membership condition (`$r is-a C`) matches any instance whose static class is in the reflexive-transitive `rdfs:subClassOf` closure of `C` (e.g., `HumanoidSub` $\sqsubseteq$ `BipedRobot` $\sqsubseteq$ `Robot`). Instance class membership and the ontology class hierarchy are fixed during execution; runtime changes apply to context values, permission models, and role assignments.
- **Domain condition thresholds:**
  - Type-dependent low-battery threshold: `($r is-a BipedRobot && $b <= 30)` OR `($r is-a WheeledRobot && $b <= 20)`.
  - Prolonged stop condition: `RobotStopped($robot, $elapsed)` with `$elapsed >= 300` (seconds, reported by an observer agent).
- **Self-delivery exclusion:** Subscribers exclude the sending agent ($S_c \setminus \{\text{sender}\}$).

---

## 2. Independent Expected Trace Table (T1–T7 / CT1–CT7)

Consumer knowledge notifications: `assert` adds a fact to the consumer's local knowledge (first supply: entry, re-entry, or a stored fact newly required after a configuration change), `update` revises the value of a fact already supplied that still satisfies the condition, and `retract` removes a supplied fact (condition exit, loss of the last supporting requirement, or source deletion). Retraction after a condition exit or a requirement change does not delete the fact from Shared Memory. Facts required under both configurations of a change receive no notification. `commit` is a configuration control message, not a knowledge notification.

| ID | Scenario & Initial Setup | Input Event / Model Transition Sequence | Independent Expected Reception Trace (`manager1`) | Independent Expected View & Fixed-Plan Decision |
|---|---|---|---|---|
| **T1 (`CT1`)**<br>Battery boundary & class/subclass | Static types: `biped1` $\in$ `BipedRobot`, `hum1` $\in$ `HumanoidSub` ($\sqsubseteq \text{BipedRobot}$), `wheel1` $\in$ `WheeledRobot`.<br>Condition: `(is-a BipedRobot && <=30)` OR `(is-a WheeledRobot && <=20)` | `e1`: `biped1` bat=31<br>`e2`: `biped1` bat=30<br>`e3`: `hum1` bat=25<br>`e4`: `wheel1` bat=25<br>`e5`: `wheel1` bat=20 | `e1`: `[]` (not entered)<br>`e2`: `[assert(biped1, 30)]`<br>`e3`: `[assert(hum1, 25)]` (subclass match)<br>`e4`: `[]` (wheeled > 20)<br>`e5`: `[assert(wheel1, 20)]` | After `e2`: `{biped1}`<br>After `e3`: `{biped1, hum1}`<br>After `e5`: `{biped1, hum1, wheel1}` |
| **T2 (`CT2`)**<br>First-argument ID constant | Condition: `RobotStatus($r, $b, $z) { $r == "wheel1"; $b <= 50; }` | `e1`: `biped1` bat=20<br>`e2`: `wheel1` bat=40<br>`e3`: `wheel1` bat=60 | `e1`: `[]` (first-arg ID mismatch)<br>`e2`: `[assert(wheel1, 40)]`<br>`e3`: `[retract(wheel1)]` | First-argument variable binds the instance key; only `wheel1` is asserted at `e2` and retracted at `e3`. |
| **T3 (`CT3`)**<br>Enter / stay / leave vs. delete | Track `biped1` under the T1 condition | `e1`: bat=30 (enter)<br>`e2`: bat=29 (stay)<br>`e3`: bat=31 (leave)<br>`e4`: bat=28 (re-enter)<br>`e5`: `op=delete` (delete) | `e1`: `[assert(v={bat:30})]`<br>`e2`: `[update(v={bat:29})]`<br>`e3`: `[retract(biped1)]` (SM retains 31)<br>`e4`: `[assert(v={bat:28})]` (re-entry)<br>`e5`: `[retract(biped1)]` (source deletion) | Both condition exit and source deletion retract the fact from the agent view; Shared Memory retains the stored value after the exit and removes it on deletion. Out-of-scope deletion produces `[]`. |
| **T4 (`CT4`)**<br>Model redeployment snapshot | Store fixed: `biped1` bat=25, `wheel1` bat=25 (no new producer reports during transitions) | `cfg0`: wheeled only (`<=20`)<br>$\to$ `cfg1`: add biped (`<=30`)<br>$\to$ `cfg2`: tighten biped (`<=20`) | `cfg0`: `[]`<br>`cfg0->1`: `[assert(biped1, 25, tr=True), commit(1)]`<br>`cfg1->2`: `[retract(biped1, tr=True), commit(2)]` | Without new producer reports, `cfg1` asserts the stored value of `biped1` before `commit(1)`, and `cfg2` retracts `biped1` from the view before `commit(2)`; the stored fact remains. |
| **T5 (`CT5`)**<br>Multi-role overlapping support | Store fixed: `biped1` bat=28.<br>`BipedMonitor` (`Biped <= 30`), `FleetMonitor` (`Robot <= 40`) | `cfg0`: `[BipedMonitor, FleetMonitor]`<br>$\to$ `cfg1`: `[FleetMonitor]` (drop `BipedMonitor`)<br>$\to$ `cfg2`: `[]` (drop `FleetMonitor`; the agent holds no role) | `cfg0`: holds `biped1`<br>`cfg0->1`: `[commit(1)]` (**no `retract`, no re-`assert`**)<br>`cfg1->2`: `[retract(biped1, tr=True), commit(2)]`; no consumer entry of the agent remains | Zero false retractions at `cfg1` while `FleetMonitor` still supports reception; retraction occurs only at `cfg2` when all supporting roles are removed. `biped1` stays stored at every step. |
| **T6 (`CT6`)**<br>`RobotStopped` elapsed time | `observer1` produces `RobotStopped($r, $elapsed)`.<br>`manager1` condition: `$elapsed >= 300` | `e1`: `wheel1` elapsed=180<br>`e2`: `wheel1` elapsed=299<br>`e3`: `wheel1` elapsed=300<br>`e4`: `wheel1` elapsed=360<br>`e5`: `wheel1` `op=delete` | `e1`: `[]`<br>`e2`: `[]`<br>`e3`: `[assert(wheel1, 300)]`<br>`e4`: `[update(wheel1, 360)]`<br>`e5`: `[retract(wheel1)]` | Entry occurs upon arrival of the observer report (`e3`), not via an internal SM timer. Fact deletion (`e5`) removes the entry from the view. |
| **T7 (`CT7-cfg0`, `CT7-cfg1`)**<br>Externally scheduled fixed-plan decisions | Fixed plan code. Decision query times ($t_1, t_2, t_3$) are injected on a fixed external schedule independent of the model | $t_1$: `biped1` bat=25 (`cfg0` unsubscribed vs. `cfg1` subscribed)<br>$t_2$: query after recovery to bat=35<br>$t_3$: query after `wheel1` elapsed=300 | `cfg1` (enabled): `assert` before $t_1$, `retract` before $t_2$, `assert(wheel1, 300)` before $t_3$.<br>`cfg0` (removal control): no reception (`[]`) | At $t_1$: `cfg1` decides `exclude`; `cfg0` decides `assign` (no low-battery evidence in view).<br>At $t_2$: `retract` clears low-battery evidence so `cfg1` decides `assign`.<br>At $t_3$: `cfg1` decides `flag_stopped`; `cfg0` decides `ok`. |

---

## 3. Edge Cases and Oracle Independence Rules

1. **Unregistered instances:** An instance ID absent from the static individual registry evaluates class membership conditions to `False` and is rejected by static checking when statically enumerable.
2. **Multiple class membership without duplicate notification:** If an individual belongs to multiple classes matching disjunctive branches, at most one `assert` or `update` notification is emitted per event (zero duplicate notifications).
3. **Cycle-safe subclass closure:** Transitive `subClassOf` evaluation uses a visited set so cyclic graphs terminate cleanly.
4. **Canonical instance IDs:** Instance keys use canonical string identifiers without `owl:sameAs` alias inference.
5. **Non-first-argument entity conditions:** Entity equality and `is-a` conditions are evaluated uniformly on any argument position (`arg_index >= 0`).
6. **Self-confirming oracle prevention:** The judge compares runtime traces directly against the pre-specified YAML files in `inputs/expected/` without importing runtime condition evaluators (`arms.d.spec`, `arms.d.smcore`, `arms.a.gl`), enforces positive reception gates where notifications are expected, and verifies that negative-control mutations fail with a non-zero exit status.
