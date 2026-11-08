# Results

Recorded on 2026-11-06 from source `wcs-v2-522e80149f03` and core snapshot `cs-core-a255c156de6c`, in containers on one host, with three parallel jobs. Only functional outcomes are judged.

| Check | Result | Record |
|---|---|---|
| 11 scenarios x D, A, H x 3 | 99 of 99 passed | `records/wcs2-3/summary.json`, `tabulation.json` |
| Negative controls (22 runs) | 22 of 22 refused by the judge as intended; not counted as passes | `records/wcs2-nc-2/summary.json` |
| Raw-log mutations | 300 detected, 0 missed, 129 not applicable | `records/wcs2-3/mutation-nc.json` |
| Static validation, no simulator | 39 of 39 as expected | `records/wcs2-3/static-check.json` |

Within each scenario the reported, notified, decided and commanded sequences were identical across arms and repetitions. "Not applicable" marks a mutation whose target a scenario does not have, such as a rejection in a scenario with no injected report. Expected notification counts by scenario are in `config/expected/`; `tabulation.json` gives observed counts and simulation and wall times.

| Scenario | Observed outcome |
|---|---|
| TR1 | Entry, value change, exit and re-entry produced assert, update, retract, assert; two crossings held and released; the zone was never co-occupied by the two robots |
| TR2 | Wheeled and Biped branches added and removed over stored locations with zero reports from the parked robots |
| TR3 | Removing one role retracted only the fact it alone supported; removing the last support retracted the other; restoring the role re-supplied the stored fact |
| TR4 | The consumer with an empty role list lost the fact, the second consumer received it with no report and continued the held request; the reverse followed |
| TR5 | Congestion 1 to 2 asserted, 2 to 3 updated, 2 to 1 retracted; lowering the threshold asserted the stored value 1 with no report; raising it retracted |
| TR6 | Biped-class robots entered at 3 s, a Wheeled robot at 5 s, and a 4 s Wheeled stop stayed below its threshold; a consumer's upper-bound exit kept the stored fact; motion deleted it; a stopped robot produced a real detour |
| TR7 | Custody passed through four robots; only Biped-class custody reached the auditor; handing to a Wheeled robot retracted; delivery deleted the fact and released the dock |
| C1 | With no reads declared the request was released at once and both robots occupied the transit zone in the same samples |
| C2 | With unconditional reads the request was never released while the other robots' facts stayed in the view |
| N1 | Invalid revisions were refused during a hold; notifications, hold and release continued under the active configuration |
| N2 | Five injected reports were refused; the store did not change and the task finished |

Screenshots are in `records/wcs2-3/<run>/shots/`. They are illustrations; verdicts come from `events.jsonl`.

## Interpretation limits

- Results are separate from the controlled core and ROS 2 evaluations and are not additive with them. Grammar cases, the condition truth table, edit effort, processing cost, process separation, transport, restart and retransmission are not covered here.
- The class signature check of `BipedBalance` is not exercised. Only multi-class selection through `hybrid1` is.
- Thresholds use short simulated durations, not operational values, and robot classes are selection types with identical motion.
- In D, Shared Memory re-evaluates stored facts. In A and H, the LTM keeps facts and the agent reloads its plans, queries the LTM and retracts locally. The consumer sees the same notifications.
- Revision checks differ by arm: D's checker, A's rule checker and H's helper. A missing source is refused by D; A and H have no equivalent check.
- The original ARBI framework was not measured.
- A release reflects the consumer's view, not a physically verified free zone.

## Runs that are not part of these results

Development runs and superseded matrices are kept outside this package. Before recording, three lower bounds on hold duration and the position of one non-causal timeline entry were corrected, one injected report was added to N2, and one stop of `wheel1` was added to TR6 so that the Wheeled threshold is reached by a robot that is not also Biped. An earlier complete matrix of 99 runs had no failures; compared with it, only the semantic sequences of TR6 changed, as intended, and the failure codes of the 22 negative controls are identical. No expected notification, decision or stored fact changed for a reason other than these additions. An earlier three-scenario package from a separate source version has its own records.
