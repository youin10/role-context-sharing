"""Shared composition API of the conditional-sharing experiment (no rclpy, no ROS).

Used by the core runner (runner/core_run.py) and by the live adapter (live/cslive), so both
build a run from the same inputs in the same way. Frozen with the core snapshot; changes need
agreement with the live worker.

  load_scenario(path)                       scenario dict (+ "_path")
  catalogue()                               (predicate catalog, TypeRegistry) from inputs/ontology
  signature()                               {context: {key, key_type, fields}} of the logistics namespace
  d_generate(d, model_map=None)             D: org model + binding -> checker -> generator (typed); (gen, provenance)
  a_dir(variant=None)                       A arm directory (inputs/models/a, or a-helper for the helper baseline)
  a_order()                                 A field order (ontology argument order)
  a_ltm(bus, guard=True)                    A LTM; guard=True = GuardedLTM (shared catalogue check, baseline helper)
  a_initial(sc, initial_map=None, arm_dir)  (initial.yml doc, provenance)
  a_initial_load(doc, agent)                load message an A agent applies at start (request_id 0)
  a_change_path(change, arm_dir)            changes/<id>.yml path of a change step
  steps(sc)                                 [init] + steps normalised to {i, id, kind, actor, ...}
  envelope(sc, step, n, ts)                 rcs-env/1 producer envelope; event_id = "<scenario>:<step id>",
                                            pv = {n: per (context, instance) counter kept by the runner, ts}
  app_factory(agent, sc)                    App: on_assert / on_update / on_retract, view(), decide(step_id)

Conventions: the core runner uses ts = step index (logical clock); the live adapter uses
time.monotonic_ns(). Ordering only compares pv within one (context, instance), so both are valid.
The fixed plan is runner/plan.py (re-exported, not a new plan).
"""
from __future__ import annotations

import hashlib
import json
import os

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("CS_ROOT") or os.path.dirname(HERE)
INPUTS = os.path.join(ROOT, "inputs")
NS = "http://ai.uos.ac.kr/logistics-ontology#"

import sys  # noqa: E402
for p in (os.path.join(ROOT, "src"), HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import plan  # noqa: E402  (runner/plan.py, the fixed decision code)

decide = plan.decide


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def sha256_json(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_scenario(path):
    with open(path) as f:
        sc = yaml.safe_load(f)
    sc["_path"] = path
    return sc


_CAT = None


def catalogue():
    global _CAT
    if _CAT is None:
        from arms.d.ontology import load_catalog, load_types
        _CAT = (load_catalog(os.path.join(INPUTS, "ontology", "predicates")),
                load_types(os.path.join(INPUTS, "ontology", "logistics-classes.ttl"),
                           os.path.join(INPUTS, "ontology", "logistics-individuals.ttl")))
    return _CAT


def signature():
    from arms.d.ontology import signature_of
    return signature_of(catalogue()[0], NS)


def d_generate(d, model_map=None, cat=None, types=None):
    from arms.d.generator import generate
    from arms.d.spec import load_binding, load_spec_org
    if cat is None or types is None:
        cat, types = catalogue()
    model = (model_map or {}).get(d["model"], d["model"])
    org = os.path.join(INPUTS, "models", "d", model + ".org")
    binding = os.path.join(INPUTS, "models", "d", d["binding"] + ".yml")
    gen = generate(load_spec_org(org, cat), load_binding(binding), types)
    return gen, {"model": model, "org_sha256": sha256_file(org), "binding": d["binding"],
                 "binding_sha256": sha256_file(binding), "gen_sha256": sha256_json(gen)}


def a_dir(variant=None):
    return os.path.join(INPUTS, "models", "a-helper" if variant == "helper" else "a")


def a_order():
    from arms.a.core import fields_from_signature
    return fields_from_signature(signature())


def a_ltm(bus, guard=True):
    from arms.a.core import LTMCore
    from arms.a.typed import GuardedLTM
    return GuardedLTM(bus, signature(), catalogue()[1]) if guard else LTMCore(bus)


def a_initial(sc, initial_map=None, arm_dir=None):
    name = (initial_map or {}).get(sc["a"]["initial"], sc["a"]["initial"])
    path = os.path.join(arm_dir or a_dir(), name + ".yml")
    with open(path) as f:
        doc = yaml.safe_load(f)
    return doc, {"initial": name, "initial_sha256": sha256_file(path)}


def a_initial_load(doc, agent):
    return {"type": "load", "request_id": 0, "change_id": "initial", "cfg": "initial",
            "roles": list(doc["agents"].get(agent, [])), "plans": doc["plans"]}


def a_change_path(change, arm_dir=None):
    base = arm_dir or a_dir()
    return os.path.join(base, change["a"] + ".yml") if "/" in change["a"] \
        else os.path.join(base, "changes", change["a"] + ".yml")


def steps(sc):
    out = [{"i": 0, "id": "init", "kind": "init", "actor": "*"}]
    for n, s in enumerate(sc["steps"], 1):
        if "report" in s or "delete" in s:
            kind = "report" if "report" in s else "delete"
            p, c, inst = s[kind][:3]
            out.append({"i": n, "id": s["id"], "kind": "report", "actor": p, "producer": p, "context": c,
                        "instance": inst, "op": "upsert" if kind == "report" else "delete",
                        "value": s[kind][3] if kind == "report" else None})
        elif "change" in s:
            out.append({"i": n, "id": s["id"], "kind": "change", "actor": "driver", "change": s["change"]})
        elif s.get("decide"):
            out.append({"i": n, "id": s["id"], "kind": "decide", "actor": sc.get("decider")})
        else:
            raise ValueError(f"unknown step {s}")
    return out


def envelope(sc, step, n, ts):
    """step: a normalised report step of steps(sc)."""
    return {"schema": "rcs-env/1", "event_id": f"{sc['id']}:{step['id']}", "producer": step["producer"],
            "pv": {"n": n, "ts": ts}, "context": step["context"], "instance": step["instance"],
            "op": step["op"], "value": step["value"]}


class App:
    """Application side shared by every arm: the eligible view plus every call it received."""

    def __init__(self, agent, sc=None):
        self.agent, self.sc = agent, sc
        self._view, self.calls = {}, []

    def on_assert(self, c, i, v, e):
        """Add a fact to the local knowledge."""
        self.calls.append(["assert", c, i, v])
        self._view[(c, i)] = v

    def on_update(self, c, i, v, e):
        """Replace the value of a fact supplied earlier."""
        self.calls.append(["update", c, i, v])
        self._view[(c, i)] = v

    def on_retract(self, c, i, cause):
        """Remove a fact from the local knowledge (the stored fact may remain in Shared Memory)."""
        self.calls.append(["retract", c, i, None])
        self._view.pop((c, i), None)

    def view(self):
        return {f"{c}/{i}": v for (c, i), v in sorted(self._view.items())}

    def decide(self, step_id=None):
        return plan.decide(self._view, (self.sc or {}).get("robots", []))


def app_factory(agent, sc):
    return App(agent, sc)
