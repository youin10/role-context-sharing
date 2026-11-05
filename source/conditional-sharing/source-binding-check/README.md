# source-binding-check — targeted static check of the source and binding validation

A separate static check, added 2026-11-03. It is **not** part of the 25 grammar cases, the 48 core runs or the 66 ROS 2 runs, and it does not change any of them.

- Purpose: show that the pre-generation checks refuse (1) a consumed context that no role declares in `changes` (`SOURCELESS`), (2) a declared reporting role with no bound agent (`INCOMPLETE_BINDING`), and (3) a binding to an undefined role (`UNKNOWN_ROLE`); that the corrected inputs are accepted with the expected reporting and consumer entries; and that a refused revision leaves an installed configuration unchanged.
- Expected outcomes: `expected.yml`, written before the first run. The accept/refuse decisions come from the method description; only the error-code names come from the checker's documented vocabulary.
- Inputs: `inputs/*.org` (role models) and `inputs/*.yml` (bindings), using the shared ontology in `../inputs/ontology`.
- Code under test: the frozen core (`src/arms/d/checker.py`, `generator.py`, `smcore.py`, `spec.py`; catalogue loader `runner/api.py`), imported read-only. This folder lies outside the snapshot members, so `tools/snapshot.py verify <id>` is unaffected.
- SB5 reproduces, with the same function calls, the order used by the core runner and the ROS 2 driver: a configuration is generated first and is staged in Shared Memory only if generation succeeds. It is a function-level check, not a ROS 2 observation.

| Case | Input | Expected |
|---|---|---|
| SB1 | consumer reads RobotStopped; no role declares it in `changes` | refused, `SOURCELESS` |
| SB1-P | Observer declares and is bound | accepted |
| SB2 | Robot declares `changes RobotStatus` but has no bound agent; only Manager is bound | refused, `INCOMPLETE_BINDING` |
| SB2-P | same model, Robot bound | accepted |
| SB3 | binding names the undefined role `Inspector` | refused, `UNKNOWN_ROLE` |
| SB3-P | that binding removed | accepted |
| SB4 | two reporting roles, only one bound | accepted (one bound source suffices) |
| SB5 | installed valid configuration, revised with the SB2 binding | revision refused; active configuration, sequence and notifications unchanged |

Run (from the core experiment root, with PyYAML):

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -I tools/snapshot.py verify <snapshot id>
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -I source-binding-check/check_source_binding.py <new run id>
```

The script writes `source-binding-check/results/<run id>/` (it refuses to overwrite) and exits 0 only if every case matches.

Records: `sb-9ec4-1` (execution-time snapshot `cs-core-9ec4e836cb48`, 8/8, freeze verified before and after, 5/5 judge mutations detected in `judge-mutations.json`) and `pub-a255-1` (public snapshot `cs-core-a255c156de6c`, 8/8, observations identical to `sb-9ec4-1`).
