"""Core (in-process, no ROS) execution of one scenario under arm D or arm A.

D path: org model (inputs/models/d) -> arms.d parser/checker/generator (with the type registry)
        -> arms.d.smcore.SMCore (reports, staged configuration changes) -> AgentCore -> app.
A path: GL role plans (inputs/models/a, or inputs/models/a-helper for the helper-built baseline)
        -> arms.a.core LTM + agents on an in-process FIFO bus; changes via changes/<id>.yml.
The FIFO bus delivers every message in send order in one process; it stands in for transport
and says nothing about the ordering a DDS deployment provides.
Both arms hand their calls to the same application (runner/api.App: eligible view + fixed
decision code runner/plan.py). Composition goes through runner/api.py, shared with live/.
"""
from __future__ import annotations

import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import api  # noqa: E402  (puts src/ on sys.path)

from arms.a.core import AAgentCore, Bus, dispatch  # noqa: E402
from arms.d.smcore import AgentCore, SMCore  # noqa: E402
from rcs.envelope import order_key  # noqa: E402

INPUTS = api.INPUTS
NS = api.NS
catalogue = api.catalogue


class DRun:
    def __init__(self, sc, variant):
        self.sc, self.v = sc, variant
        self.sm_cls = variant.get("sm_cls", SMCore)
        self.agents, self.apps = {}, {}
        self.seq = 0

    def gen(self, model, binding):
        return api.d_generate({"model": model, "binding": binding}, self.v.get("model_map"))

    def start(self):
        g, prov = self.gen(self.sc["d"]["model"], self.sc["d"]["binding"])
        self.sm = self.sm_cls(g)
        self._agents(g)
        return {**prov, "consumers": g["consumers"]}

    def _agents(self, g):
        for a in g["agents"]:
            if a not in self.agents:
                self.agents[a] = AgentCore()
                self.apps[a] = api.app_factory(a, self.sc)

    def deliver(self, out):
        msgs = []
        for agent, m in out:
            msgs.append([agent, m])
            calls, ack = self.agents[agent].handle(m)
            for call in calls:
                getattr(self.apps[agent], call[0])(*call[1:])
            if ack:
                self.sm.ack(agent, ack)
        return msgs

    def report(self, env):
        before = len(self.sm.rejected)
        out = self.sm.report(env)
        return self.deliver(out), self.sm.rejected[before:]

    def change(self, ch, now):
        if self.v.get("skip_changes"):
            return [], {"skipped": True}
        g, prov = self.gen(ch["d"]["model"], ch["d"]["binding"])
        self._agents(g)
        self.seq += 1
        return self.deliver(self.sm.stage(self.seq, g, ch["id"], now)), {"seq": self.seq, **prov,
                                                                         "consumers": g["consumers"]}

    def store(self):
        return {f"{c}/{i}": v for c, d in sorted(self.sm.store.items()) for i, (v, e) in sorted(d.items())}


class ARun:
    def __init__(self, sc, variant):
        self.sc, self.v = sc, variant
        self.arm_dir = api.a_dir(variant.get("a_variant"))
        self.rid = 0

    def start(self):
        self.bus = Bus()
        self.ltm = api.a_ltm(self.bus, self.v.get("guard", True))
        order = api.a_order()
        ini, prov = api.a_initial(self.sc, self.v.get("initial_map"), self.arm_dir)
        self.apps, self.agents = {}, {}
        for a in ini["agents"]:
            self.apps[a] = api.app_factory(a, self.sc)
            self.agents[a] = AAgentCore(a, self.bus, self.apps[a], order, self.arm_dir, asis=self.v.get("asis", False))
        for a in ini["agents"]:
            self.agents[a]._load(api.a_initial_load(ini, a))
        self.bus.pump()
        return {**prov, "arm_dir": os.path.relpath(self.arm_dir, INPUTS), "plans": ini["plans"],
                "guard": self.v.get("guard", True), "asis": self.v.get("asis", False)}

    def report(self, env):
        before = len(getattr(self.ltm, "rejected", []))
        sent = self.bus.sent
        self.agents[env["producer"]].emit(env)
        self.bus.pump()
        return [{"bus_messages": self.bus.sent - sent}], getattr(self.ltm, "rejected", [])[before:]

    def change(self, ch, now):
        if self.v.get("skip_changes"):
            return [], {"skipped": True}
        self.rid += 1
        path = api.a_change_path(ch, self.arm_dir)
        sent = self.bus.sent
        targets = dispatch(self.bus, self.arm_dir, path, self.rid, ch["id"])
        self.bus.pump()
        acks = {a: self.agents[a].acks[-1] if self.agents[a].acks else None for a in targets}
        return [{"bus_messages": self.bus.sent - sent}], {"targets": targets, "acks": acks,
                                                          "change_sha256": api.sha256_file(path)}

    def store(self):
        facts, tombs = {}, {}
        for (name, key), (fact, text, env) in self.ltm.latest.items():
            if env is None:
                continue
            x = f"{env['context']}/{env['instance']}"
            (tombs if name == "deleted" else facts)[x] = env
        out = {}
        for x, env in sorted(facts.items()):
            t = tombs.get(x)
            if t is None or order_key(t) < order_key(env):
                out[x] = env["value"]
        return out


def run(sc_path, arm, variant, out_path, label):
    sc = sc_path if isinstance(sc_path, dict) else api.load_scenario(sc_path)
    r = (DRun if arm == "D" else ARun)(sc, variant)
    rows = []
    err = None
    ctx = variant.get("context")
    try:
        if ctx is not None:
            ctx.__enter__()
        info = r.start()
        rows.append({"rec": "start", "scenario": sc["id"], "arm": arm, "variant": label,
                     "observe": sc["observe"], "setup": info})
        n = {}
        for step in api.steps(sc)[1:]:
            k = step["i"]
            rec = {"rec": "step", "step": step["id"], "k": k}
            marks = {a: len(app.calls) for a, app in r.apps.items()}
            if step["kind"] == "report":
                x = (step["context"], step["instance"])
                n[x] = n.get(x, 0) + 1
                env = api.envelope(sc, step, n[x], k)
                rec["input"] = env
                rec["out"], rec["rejected"] = r.report(env)
            elif step["kind"] == "change":
                out, meta = r.change(step["change"], float(k))
                rec["input"] = {"change": step["change"]["id"]}
                rec["out"], rec["change"] = out, meta
            elif step["kind"] == "decide":
                rec["decide"] = True
                rec["decision"] = r.apps[step["actor"]].decide(step["id"])
            rec["calls"] = {a: app.calls[marks.get(a, 0):] for a, app in r.apps.items()
                            if app.calls[marks.get(a, 0):]}
            rec["views"] = {a: r.apps[a].view() for a in sc["observe"] if a in r.apps}
            rec["store"] = r.store()
            rows.append(rec)
    except Exception as e:                      # recorded, judged as a failure, never hidden
        err = f"{type(e).__name__}: {e}"
        rows.append({"rec": "error", "trace": traceback.format_exc()})
    finally:
        if ctx is not None:
            ctx.__exit__(None, None, None)
    end = {"rec": "end", "error": err}
    if arm == "D" and err is None:
        end["sm_stats"] = r.sm.stats
    if arm == "A" and err is None:
        end["ltm_counts"] = r.ltm.counts
        end["agent_counts"] = {a: {"subscriptions": ag.n_sub, "matches": ag.n_req, "watches": len(ag.watch)}
                               for a, ag in sorted(r.agents.items())}
    rows.append(end)
    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    return rows
