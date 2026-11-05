# core ↔ live API (runner/api.py, rclpy-free)

Shared assembly interface between the in-process core runner and the ROS 2 live runner. Frozen with the core snapshot (see snapshots/).

1. App: `api.app_factory(agent, sc) -> App` with `on_assert / on_update / on_retract`,
   `view() -> {"Ctx/inst": value}`, `decide(step_id) -> plan.decide(view, sc["robots"])`
   (runner/plan.py, the existing fixed plan). Live: `CS_APP=api:app_factory`, `runner/` on PYTHONPATH,
   `CS_ROOT=<experiments/conditional-sharing>` (api derives inputs/ and src/ from it).
2. Composition: `load_scenario`, `catalogue() -> (catalog, types)`, `signature()`,
   `d_generate(d, model_map=None) -> (gen, provenance)`, `a_dir(None | "helper")`, `a_order()`,
   `a_ltm(bus, guard=True)` (GuardedLTM = shared catalogue check), `a_initial(sc, initial_map, arm_dir)`,
   `a_initial_load(doc, agent)`, `a_change_path(change, arm_dir)`, `steps(sc)` (init + report/change/decide;
   a delete is kind=report with op=delete — same normalisation as live/cslive/build.steps),
   `envelope(sc, step, n, ts)`.
3. Envelope convention: `event_id = "<scenario>:<step id>"` (the live convention), `pv = {n, ts}` with n per
   (context, instance) (counter kept by the runner); core ts = step index, live ts = time.monotonic_ns(). Receivers compare pv only
   within one (context, instance), so both are valid.
4. `src/arms/a/agent.py`, `ltm.py` (import rcs.rosproc, not runnable here) removed from src/; originals stay in upstream/.
Also new: the core judge enforces the scenario-file roster and step order; scenario X2 (BipedBalance/hybrid1);
helper A baseline under inputs/models/a-helper (`api.a_dir("helper")`).
