# Design

## Purpose

Each scenario closes the loop through the simulator: scene poses become reports, reports become consumer notifications, a shared routine decides, and the decision moves a robot. Report values come from the running world. Scenario files fix tasks and requirement changes, not reported values.

```
Webots scene -> observer -> derived facts -> rcs-env/1 reports
  -> D: SMCore / A, H: LTM + AAgentCore -> assert / update / retract
  -> shared routine -> MQTT command -> Webots motion -> ...
```

## Facts

Predicates and classes are the core ontology's, unchanged. The file `config/ontology/simulator-individuals.ttl` adds one individual, `apron_zone`.

| Predicate | Producer | Derived from |
|---|---|---|
| `RobotLocatedAt(robot, node)` | each robot | Scene pose mapped to a cell, on change |
| `ZoneStatus(zone, congestion, access)` | `cam1` | Number of robots in the `apron` cell, on change |
| `RobotStopped(robot, elapsedSeconds)` | `cam1` | Whole seconds a robot with an active task has not moved |
| `CargoCarriedBy(cargo, robot)` | carrying robot | Raised cargo pose and the nearest robot |

`config/topology.yml` maps poses to cells with a total deterministic function:

| y \ x | [-15,-3) | [-3,0) | [0,3) | [3,15) |
|---|---|---|---|---|
| [1.5,10) | `bay_nw` | `hold_n` | `hold_n` | `apron` |
| [-1.5,1.5) | `aisle_w` | `t_w` | `t_e` | `aisle_e` |
| [-10,-1.5) | `bay_sw` | `hold_s` | `hold_s` | `bay_se` |

Simulated robots use the names of registered individuals: `wheel1`, `wheeled1` (Wheeled), `diff1` (DifferentialDrive), `humanoid1` (Humanoid), `biped1` (Biped), `hybrid1` (Biped and Wheeled). Classes are selection types only. Every robot has the same box body and the same kinematic motion at 2 m/s of simulation time. Heterogeneous dynamics are not modelled.

A fact is deleted only for a stated cause: `RobotStopped` when the robot moves again, `CargoCarriedBy` when the cargo is put down. Loss of observation never deletes a fact.

## Routine

While a request is pending, facts of its blocking contexts hold it. A `RobotLocatedAt` fact about the requesting robot itself does not count. With no blocking fact the request is released. The detour policy takes an alternative path instead of waiting. The routine is fixed, reads only the coordinating agent's view, and is identical across arms. The method does not synthesize plans.

## Scenarios

`TR*` are transport and zone-coordination tasks. `C*` are contrasts. `N*` are explicit negative tests, whose injected reports and refused revisions are logged apart from normal reports.

| ID | Purpose | Behaviour |
|---|---|---|
| TR1 | Transit-zone hold and release | Entry, value change, exit, re-entry |
| TR2 | Requirement revisions | Wheeled and Biped branches added and removed over stored locations with no report |
| TR3 | Overlapping roles | Unsupported fact retracted, supported fact kept, last support removed, role restored |
| TR4 | Coordination reassigned | Empty role list, second consumer takes over, then back |
| TR5 | Congestion-limited entry | Numeric boundary, threshold revision over a stored value |
| TR6 | Stops on a lane | Typed thresholds, upper-bound exit versus deletion, detour |
| TR7 | Cargo custody | Non-key entity argument, individual constant, class negation, four consumers, delivery deletes the fact |
| C1 | No reads declared | Immediate release, zone co-occupied |
| C2 | Unconditional reads | Over-supply, request never released |
| N1 | Invalid redeployment during a hold | Refused, active configuration and task continue |
| N2 | Malformed reports during a hold | Refused, store unchanged, task continues |

### Scenario details

All runs start from the same world: `wheel1 (-9,-5)`, `humanoid1 (-12,-5)`, `biped1 (-6,-5)`, `hybrid1 (-12,5)`, `wheeled1 (1.5,6)`, `diff1 (7,-5)`, and `cargo1` on the floor at `(-9,-8)`. The full step lists are in `config/scenarios/`, and every expected value is in `config/expected/`. The transit zone is `t_w` and `t_e`; `apron` is a parking area next to it.

**TR1, transit zone.** `manager1` reads locations in the zone. `wheel1` drives east along the aisle. When it enters `t_w`, `wheeled1` asks to cross southward and is held. The fact changes from `t_w` to `t_e`; when `wheel1` leaves, the fact is retracted and `wheeled1` crosses. `wheel1` then returns westward, re-enters the zone and is asserted again, and `wheeled1` waits for its northbound crossing the same way.

**TR2, requirement revisions.** `diff1` (Wheeled) and `humanoid1` (Biped subclass) park on `apron`, outside the requirement. A southbound crossing is released at once. Revision `r1` adds a Wheeled branch for `apron`: `diff1`'s stored fact is asserted and the northbound request holds. Revision `r2` adds a Biped branch: `humanoid1` is asserted. The revisions are then undone one at a time, retracting each fact, and the last one releases the crossing. Each revision waits until both robots have been stationary for 1 s; no report from them may fall between that check and the notification.

**TR3, overlapping roles.** `manager1` holds `TransitCoordinator`, `ApronSupervisor` (any robot on `apron`) and `ApronInspector` (Wheeled robots on `apron`). `diff1` is supported by both apron roles, `humanoid1` only by the supervisor. Removing the supervisor retracts `humanoid1` and keeps `diff1`. Removing the inspector retracts `diff1` and releases the crossing. Restoring the inspector re-supplies `diff1`'s stored fact with no report and holds the return crossing until `diff1` actually leaves.

**TR4, coordination reassigned.** `wheel1` parks in the zone and `wheeled1` is held by `manager1`. The binding moves `TransitCoordinator` to `manager2`, leaving `manager1` with an empty role list. `manager1` gets a retract, `manager2` gets the stored fact with no report and keeps the request held. `manager2` releases it when `wheel1` leaves. The binding is later reversed in the same way.

**TR5, congestion-limited entry.** `cam1` reports how many robots are on `apron`. `manager1` reads that value at 2 or more. Three robots enter, giving 1 (not selected), 2 (assert, boundary) and 3 (update). `wheeled1` is held from entering. Robots leave: 2 (update), 1 (retract, release). With one robot left and nothing moving, the threshold is lowered to 1: the stored value 1 is asserted with no report and the next entry is held. Raising the threshold retracts it and releases the entry.

**TR6, stops on a lane.** A robot with an active task that stops moving is reported each whole second. `manager1` reads Biped robots from 3 s and Wheeled robots from 5 s. `watch1` reads stops of 2 to 4 s. `humanoid1` stops in the zone for 6 s: at 5 s `watch1` loses the fact by condition exit while it stays stored, and when the robot moves on the observer deletes it. During that stop a crossing request takes a detour through `t_w`; a later request goes straight. `diff1` stops for 4 s, below its threshold, so `watch1` loses the fact only by deletion. `hybrid1`, which is both Biped and Wheeled, stops for 6 s and receives one notification per report. `wheel1` stops for 6 s and reaches the Wheeled threshold at 5 s.

**TR7, cargo custody.** `wheel1` lifts `cargo1`, `humanoid1` takes it, `biped1` takes it and carries it east, `diff1` takes it and puts it down at its destination. `manager1` reads every carrier, `auditor1` only Biped-class carriers, `tech1` the location of `biped1`, `watch1` non-Biped robots in `hold_s`. Handing to `diff1` makes `auditor1` lose the fact by condition exit. Putting the cargo down deletes the fact, and that releases the held `wheeled1`.

**C1, no reads.** The trace of TR1's first crossing with an empty reads declaration. The request is released at once and both robots are in the zone in the same samples. This shows the role of the requirement, not a collision result.

**C2, unconditional reads.** The same trace with an unconditional reads declaration. Every robot's location reaches `manager1`, and the unchanged routine never releases the request.

**N1, invalid redeployment.** During a hold, one revision with an unregistered individual is refused by each arm's pre-deployment check, and on D a revision without a bound source is also refused. Nothing is installed. The active configuration then releases the request as usual.

**N2, malformed reports.** During a hold, five reports are injected: unregistered robot, wrong class, ill-typed value, wrong field, unregistered non-key entity. They are logged as injections, not as observations. All are refused, the store does not change, and the task finishes.

## Arms

- **D**: `.org` model and binding through the frozen parser, checker and generator.
- **A**: hand-authored explicit subscription rules (`config/a-hand`) on a Python implementation of ARBI-style rules. This is not a measurement of the original ARBI framework.
- **H**: the same runtime with rules generated by the core's helper from type-level inputs (`config/a-helper/source`).

Revisions are checked before deployment by D's checker, A's rule checker and H's helper. A and H have no check for a missing source, so that case runs on D only.

## Judging

Expected tables in `config/expected/` are fixed before the recorded matrix. `tools/judge.py` reads raw events only. It re-derives report values from sampled poses and checks per-consumer notification order, change windows, checkpoints, final stores and views, hold and motion, co-occupancy, command order, arrivals and refusal codes.

## Scope

Motion is a kinematic position update. The sharing layer runs in one process with an in-order bus; MQTT only connects the simulator. Sensing, collision avoidance, safety, physical scalability, communication faults and distributed ordering are not evaluated. Grammar coverage, truth tables, edit effort and processing cost remain with the core evaluation.
