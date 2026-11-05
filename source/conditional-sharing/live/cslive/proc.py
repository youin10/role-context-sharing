"""Live processes: the in-memory cores (src/arms/d/smcore.py, src/arms/a/core.py) hosted in
separate rclpy processes, composed through runner/api.py exactly as the core runner composes
them; every core-to-core message travels over DDS instead of the core runner's FIFO bus. The
adapter adds no routing, condition, view or decision logic:
  D  d-sm       SMCore(api.d_generate(EBNF model)) — report / stage / ack / due
     d-producer api.envelope of producer writes + AgentCore/App of every unobserved agent
     d-agent-X  AgentCore + api.app_factory App of observed agent X (decide = runner/plan.py)
     driver     step control, applier (api.d_generate(changed model) -> /d/apply), capture
  A  a-ltm      api.a_ltm (GuardedLTM by default)
     a-producer AAgentCore of every unobserved agent of the initial A file
     a-agent-X  AAgentCore + App of observed agent X
     driver     step control, dispatcher (arms.a.core.dispatch over the wire), capture
Step protocol: `arm` (every process sets the step id and answers ready) -> `go` (the actor
acts) -> settle: the driver probes every process for its per-topic tx/rx counters and core
state until (1) every data message sent so far was received by every subscriber (message
conservation), (2) the step's core completion holds (D change: committed and acknowledged by
every agent; A change: every target acknowledged its load; A: no outstanding match request),
and (3) two consecutive probes agree. Every process writes a raw JSONL log of all messages
it sends and receives (with payload hashes), every application call with the inbox message
that caused it, core state after each step, and final statistics.

  CS_RUN=/run CS_PROC=<name> python3 -m cslive.proc     (plan in /run/plan.json)
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time

import rclpy
import rclpy.utilities
from std_msgs.msg import String

import api
from cslive import wire

HELLO_TIMEOUT_S = 90.0
READY_TIMEOUT_S = 30.0
PROBE_TIMEOUT_S = 10.0
STEP_TIMEOUT_S = 60.0
PROBE_GAP_S = 0.05


def h(data):
    return hashlib.sha256(data.encode()).hexdigest()


def topology(plan):
    """{topic: (publisher procs, subscriber procs)}; the driver captures every data topic."""
    arm, procs = plan["arm"], plan["procs"]
    host = {a: p for p, ags in procs.items() for a in ags}
    workers = [p for p in procs if p != "driver"]
    t = {wire.CTL: ({"driver"}, set(workers)), wire.READY: (set(workers), {"driver"})}
    agent_procs = {p for p in procs if p.startswith(f"{arm}-agent-") or p == f"{arm}-producer"}
    if arm == "d":
        t[wire.D_REPORT] = ({host[a] for a in plan["producers"]}, {"d-sm", "driver"})
        t[wire.D_APPLY] = ({"driver"}, {"d-sm"})
        t[wire.D_ACK] = (set(agent_procs), {"d-sm", "driver"})
        for a in plan["agents"]:
            t[wire.d_inbox(a)] = ({"d-sm"}, {host[a], "driver"})
    else:
        t[wire.A_LTM] = (set(agent_procs), {"a-ltm", "driver"})
        for a in plan["agents"]:
            t[wire.a_inbox(a)] = ({"a-ltm", "driver"}, {host[a], "driver"})
    return {k: (sorted(p), sorted(s)) for k, (p, s) in t.items()}


class Log:
    def __init__(self, path, proc):
        self.f = open(path, "a")
        self.proc = proc
        self.step = None
        self.n = 0

    def write(self, kind, **kw):
        self.n += 1
        self.f.write(wire.dumps({"seq": self.n, "t_ns": time.monotonic_ns(), "proc": self.proc,
                                 "step": self.step, "kind": kind, **kw}) + "\n")
        self.f.flush()

    def close(self):
        self.f.close()


class Recorder:
    """Wraps the core application (api.app_factory): logs every call with the inbox message
    being processed when it happened, then forwards it unchanged."""

    def __init__(self, agent, proc, inner):
        self.agent, self.proc, self.inner = agent, proc, inner

    def _log(self, call, c, i, v, **kw):
        self.proc.log.write("call", agent=self.agent, call=call, c=c, i=i, v=v, cause=self.proc.cause, **kw)

    def on_assert(self, c, i, v, e):
        self._log("assert", c, i, v, e=e)
        self.inner.on_assert(c, i, v, e)

    def on_update(self, c, i, v, e):
        self._log("update", c, i, v, e=e)
        self.inner.on_update(c, i, v, e)

    def on_retract(self, c, i, cause):
        self._log("retract", c, i, None, n=cause)
        self.inner.on_retract(c, i, cause)


class RosBus:
    """arms.a.core.Bus replacement: send() publishes instead of queueing (same interface)."""

    def __init__(self, proc):
        self.proc, self.nodes, self.sent = proc, {}, 0

    def send(self, dest, d):
        self.sent += 1
        self.proc.publish(wire.A_LTM if dest == "ltm" else wire.a_inbox(dest), d)


class Proc:
    def __init__(self, run_dir, name):
        self.run_dir, self.name = run_dir, name
        with open(os.path.join(run_dir, "plan.json")) as f:
            self.plan = json.load(f)
        self.sc = api.load_scenario(self.plan["scenario_path"])
        self.arm = self.plan["arm"]
        self.hosted = self.plan["procs"][name]
        self.log = Log(os.path.join(run_dir, "logs", f"{name}.jsonl"), name)
        rclpy.init()
        self.node = rclpy.create_node("cs_" + name.replace("-", "_"), enable_rosout=False,
                                      start_parameter_services=False)
        self.topo = topology(self.plan)
        self.data_topics = set(wire.data_topics(self.plan))
        self.pubs = {}
        self.tx, self.rx = {}, {}
        self.cause = None
        self.done = False
        self.step = None
        self.log.write("env", rmw=rclpy.utilities.get_rmw_implementation_identifier(),
                       domain=os.environ.get("ROS_DOMAIN_ID"), host=os.uname().nodename, pid=os.getpid(),
                       python=sys.version.split()[0], qos=wire.QOS_DESC, hosted=self.hosted,
                       api_sha256=api.sha256_file(api.__file__))

    # transport ------------------------------------------------------------------------
    def publish(self, topic, obj):
        data = wire.dumps(obj)
        self.pubs[topic].publish(String(data=data))
        if topic in self.data_topics:
            self.tx[topic] = self.tx.get(topic, 0) + 1
        self.log.write("tx", topic=topic, h=h(data), data=data)

    def subscribe(self, topic, cb):
        def on(msg):
            hh = h(msg.data)
            if topic in self.data_topics:
                self.rx[topic] = self.rx.get(topic, 0) + 1
            self.log.write("rx", topic=topic, h=hh, data=msg.data)
            self.cause = {"topic": topic, "h": hh, "rx_seq": self.log.n}
            try:
                cb(json.loads(msg.data))
            finally:
                self.cause = None
        self.node.create_subscription(String, topic, on, wire.QOS)

    def open_topics(self, handlers):
        for topic, (pubs, subs) in self.topo.items():
            if self.name in pubs:
                self.pubs[topic] = self.node.create_publisher(String, topic, wire.QOS)
            if self.name in subs:
                self.subscribe(topic, handlers.get(topic, lambda d: None))

    def wait_matched(self):
        """Discovery barrier: own publishers see all their subscribers, own subscriptions see
        all their publishers."""
        end = time.monotonic() + HELLO_TIMEOUT_S
        while True:
            missing = []
            for topic, (pubs, subs) in self.topo.items():
                if self.name in pubs and self.pubs[topic].get_subscription_count() < len(subs):
                    missing.append(("pub", topic))
                if self.name in subs and self.node.count_publishers(topic) < len(pubs):
                    missing.append(("sub", topic))
            if not missing:
                self.log.write("matched")
                return
            if time.monotonic() > end:
                self.log.write("match_timeout", missing=missing)
                raise RuntimeError(f"{self.name}: discovery timeout {missing}")
            rclpy.spin_once(self.node, timeout_sec=0.05)

    def spin(self):
        while not self.done:
            rclpy.spin_once(self.node, timeout_sec=0.01)
            self.tick()

    def tick(self):
        pass

    def close(self):
        self.log.write("exit")
        self.log.close()
        self.node.destroy_node()
        rclpy.shutdown()


class Worker(Proc):
    """Every process except the driver: follows the control topic."""

    def on_ctl(self, d):
        ph = d["phase"]
        if ph == "arm":
            self.log.write("state", after=self.step and self.step["id"], **self.state())
            self.step = d["step"]
            self.log.step = self.step["id"]
            self.publish(wire.READY, {"proc": self.name, "i": self.step["i"]})
        elif ph == "go":
            s = self.step
            if s["actor"] == "*" or s["actor"] in self.hosted:
                self.log.write("act", what=s["kind"])
                self.act(s)
        elif ph == "probe":
            self.publish(wire.READY, {"proc": self.name, "probe": d["n"], "tx": self.tx, "rx": self.rx,
                                      "status": self.status()})
        elif ph == "end":
            self.log.write("state", after=self.step and self.step["id"], **self.state())
            self.log.write("final", **self.final())
            self.done = True

    def start(self, handlers):
        handlers[wire.CTL] = self.on_ctl
        self.open_topics(handlers)
        self.wait_matched()
        self.publish(wire.READY, {"proc": self.name, "i": -1})
        self.spin()
        self.close()

    def act(self, s):
        pass

    def state(self):
        return {}

    def status(self):
        return {}

    def final(self):
        return {}


class AppHost(Worker):
    """Shared by the D and A agent processes: apps, decision, views."""

    def make_apps(self):
        self.apps = {a: Recorder(a, self, api.app_factory(a, self.sc)) for a in self.hosted}

    def decide(self, s):
        self.log.write("decision", agent=s["actor"], decision=self.apps[s["actor"]].inner.decide(s["id"]))

    def state(self):
        return {"views": {a: self.apps[a].inner.view() for a in self.hosted if a in self.plan["observed"]}}


# D ---------------------------------------------------------------------------------------
class DSM(Worker):
    def run(self):
        from arms.d.smcore import SMCore
        gen, prov = api.d_generate(self.sc["d"])
        self.log.write("generated", seq=0, cfg=gen["cfg"], **prov)
        self.core = SMCore(gen)
        self.start({wire.D_REPORT: self.on_report, wire.D_APPLY: self.on_apply, wire.D_ACK: self.on_ack})

    def _send(self, out):
        for agent, m in out:
            self.publish(wire.d_inbox(agent), m)

    def on_report(self, env):
        before = len(self.core.rejected)
        out = self.core.report(env)
        if len(self.core.rejected) > before:
            self.log.write("rejected", rejected=self.core.rejected[before:])
        self._send(out)

    def on_apply(self, d):
        self.log.write("stage", seq=d["seq"], change_id=d["change_id"], gen_sha256=api.sha256_json(d["gen"]))
        self._send(self.core.stage(d["seq"], d["gen"], d["change_id"], time.monotonic()))

    def on_ack(self, d):
        done = self.core.ack(d["agent"], d["seq"])
        if done:
            self.log.write("committed_all", done=done)

    def tick(self):
        out, late = self.core.due(time.monotonic())
        if late:
            self.log.write("deadline_overrun", late=late)
        self._send(out)

    def state(self):
        return {"store": {f"{c}/{i}": v for c, d in sorted(self.core.store.items()) for i, (v, e) in sorted(d.items())}}

    def status(self):
        return {"active_seq": self.core.active.seq, "pending": sorted(self.core.pending),
                "staged": sorted(self.core.staged)}

    def final(self):
        return {"stats": self.core.stats, "rejected": self.core.rejected, "outside": self.core.outside,
                "active_seq": self.core.active.seq, "pending": sorted(self.core.pending)}


class DAgents(AppHost):
    def run(self):
        from arms.d.smcore import AgentCore
        self.cores = {a: AgentCore() for a in self.hosted}
        self.make_apps()
        self.n = {}
        self.start({wire.d_inbox(a): (lambda d, a=a: self.on_msg(a, d)) for a in self.hosted})

    def on_msg(self, agent, m):
        calls, ack = self.cores[agent].handle(m)
        for name, *args in calls:
            getattr(self.apps[agent], name)(*args)
        if ack:
            self.publish(wire.D_ACK, {"agent": agent, "seq": ack})

    def act(self, s):
        if s["kind"] == "report":
            x = (s["context"], s["instance"])           # per-item counter, as runner/core_run.py
            self.n[x] = self.n.get(x, 0) + 1
            self.publish(wire.D_REPORT, api.envelope(self.sc, s, self.n[x], time.monotonic_ns()))
        elif s["kind"] == "decide":
            self.decide(s)

    def status(self):
        return {a: {"applied_seq": c.applied_seq} for a, c in self.cores.items()}

    def final(self):
        return {a: {"applied_seq": c.applied_seq, "dups": c.dups, "gaps": c.gaps,
                    "retracts_not_held": c.retracts_not_held, "held": sorted(map(list, c.held))}
                for a, c in self.cores.items()}


# A ---------------------------------------------------------------------------------------
class ALTM(Worker):
    def run(self):
        self.bus = RosBus(self)
        self.core = api.a_ltm(self.bus, guard=os.environ.get("CS_A_GUARD", "1") == "1")
        self.start({wire.A_LTM: self.on_req})

    def on_req(self, d):
        rej = getattr(self.core, "rejected", [])
        before = len(rej)
        self.core.receive(d)
        if len(rej) > before:
            self.log.write("rejected", rejected=rej[before:])

    def state(self):
        import types
        import core_run
        return {"store": core_run.ARun.store(types.SimpleNamespace(ltm=self.core))}

    def status(self):
        return {"counts": self.core.counts}

    def final(self):
        return {"counts": self.core.counts, "rejected": getattr(self.core, "rejected", []), "subs": len(self.core.subs)}


class AAgents(AppHost):
    def run(self):
        from arms.a.core import AAgentCore
        self.bus = RosBus(self)
        self.arm_dir = api.a_dir(self.plan.get("a_variant"))
        self.initial, prov = api.a_initial(self.sc, None, self.arm_dir)
        self.log.write("a_initial", arm_dir=self.arm_dir, **prov)
        order = api.a_order()
        self.make_apps()
        self.cores = {a: AAgentCore(a, self.bus, self.apps[a], order, self.arm_dir) for a in self.hosted}
        self.n = {}
        self.start({wire.a_inbox(a): self.cores[a].receive for a in self.hosted})

    def act(self, s):
        if s["kind"] == "init":
            for a in self.hosted:
                self.cores[a]._load(api.a_initial_load(self.initial, a))
        elif s["kind"] == "report":
            x = (s["context"], s["instance"])
            self.n[x] = self.n.get(x, 0) + 1
            self.cores[s["producer"]].emit(api.envelope(self.sc, s, self.n[x], time.monotonic_ns()))
        elif s["kind"] == "decide":
            self.decide(s)

    def status(self):
        return {a: {"acks": [x["request_id"] for x in c.acks], "pending": len(c.pending), "buffer": len(c.buffer)}
                for a, c in self.cores.items()}

    def final(self):
        return {a: {"acks": c.acks, "log": c.log, "held": sorted(map(list, c.held)), "subscriptions": c.n_sub,
                    "matches": c.n_req, "watches": len(c.watch)} for a, c in self.cores.items()}


# driver ----------------------------------------------------------------------------------
class Driver(Proc):
    def run(self):
        self.ready, self.probes = {}, {}
        self.workers = [p for p in self.plan["procs"] if p != "driver"]
        self.bus = RosBus(self) if self.arm == "a" else None
        self.arm_dir = api.a_dir(self.plan.get("a_variant"))
        self.seq = 0
        self.probe_n = 0
        self.open_topics({wire.READY: self.on_ready})
        self.wait_matched()
        self.wait_ready(-1, HELLO_TIMEOUT_S)
        self.log.write("all_hello")
        steps = api.steps(self.sc)
        for s in steps:
            self.log.step = s["id"]
            self.publish(wire.CTL, {"phase": "arm", "step": s})
            self.wait_ready(s["i"], READY_TIMEOUT_S)
            self.publish(wire.CTL, {"phase": "go", "i": s["i"]})
            target = self.change(s) if s["kind"] == "change" else None
            self.settle(s, target)
        self.log.step = None
        self.publish(wire.CTL, {"phase": "end"})
        t = time.monotonic() + 2.0
        while time.monotonic() < t:
            rclpy.spin_once(self.node, timeout_sec=0.05)
        self.log.write("final", steps=len(steps))
        self.close()

    def on_ready(self, d):
        if "probe" in d:
            self.probes.setdefault(d["probe"], {})[d["proc"]] = d
        else:
            self.ready.setdefault(d["i"], set()).add(d["proc"])

    def wait_ready(self, i, timeout):
        end = time.monotonic() + timeout
        while set(self.workers) - self.ready.get(i, set()):
            if time.monotonic() > end:
                self.log.write("ready_timeout", i=i, missing=sorted(set(self.workers) - self.ready.get(i, set())))
                raise RuntimeError(f"ready timeout at step {i}")
            rclpy.spin_once(self.node, timeout_sec=0.01)

    def probe(self):
        self.probe_n += 1
        n = self.probe_n
        self.publish(wire.CTL, {"phase": "probe", "n": n})
        end = time.monotonic() + PROBE_TIMEOUT_S
        while set(self.workers) - set(self.probes.get(n, {})):
            if time.monotonic() > end:
                raise RuntimeError(f"probe {n} timeout")
            rclpy.spin_once(self.node, timeout_sec=0.005)
        rep = self.probes.pop(n)
        rep["driver"] = {"tx": dict(self.tx), "rx": dict(self.rx), "status": {}}
        return rep

    def conserved(self, rep):
        """Every data message any process sent was received by every subscriber of its topic."""
        bad = []
        for topic, (pubs, subs) in self.topo.items():
            if topic not in self.data_topics:
                continue
            sent = sum(rep[p]["tx"].get(topic, 0) for p in pubs)
            for s in subs:
                if rep[s]["rx"].get(topic, 0) != sent:
                    bad.append([topic, s, sent, rep[s]["rx"].get(topic, 0)])
        return bad

    def complete(self, s, target, rep):
        """Core completion of the step (beyond message conservation)."""
        if self.arm == "d":
            st = rep["d-sm"]["status"]
            if st["pending"] or st["staged"]:
                return False
            return target is None or st["active_seq"] >= target
        agents = {a: v for p in self.workers if p != "a-ltm" for a, v in rep[p]["status"].items()}
        if any(v["pending"] or v["buffer"] for v in agents.values()):
            return False
        if target is not None:
            rid, targets = target
            return all(rid in agents[a]["acks"] for a in targets)
        return True

    def settle(self, s, target):
        start = time.monotonic()
        prev, n = None, 0
        while True:
            rep = self.probe()
            n += 1
            bad = self.conserved(rep)
            ok = not bad and self.complete(s, target, rep)
            counts = {p: [r["tx"], r["rx"]] for p, r in rep.items()}
            if ok and prev == counts:
                self.log.write("settled", i=s["i"], dt_s=round(time.monotonic() - start, 4), probes=n,
                               target=target, counts=counts,
                               status={p: r["status"] for p, r in rep.items() if r["status"]})
                return
            prev = counts if ok else None
            if time.monotonic() - start > STEP_TIMEOUT_S:
                self.log.write("step_timeout", i=s["i"], unconserved=bad, counts=counts,
                               status={p: r["status"] for p, r in rep.items()})
                raise RuntimeError(f"step {s['id']} did not settle")
            t = time.monotonic() + PROBE_GAP_S
            while time.monotonic() < t:
                rclpy.spin_once(self.node, timeout_sec=0.005)

    def change(self, s):
        ch = s["change"]
        self.seq += 1
        if self.arm == "d":
            gen, prov = api.d_generate(ch["d"])
            self.log.write("generated", seq=self.seq, change_id=ch["id"], cfg=gen["cfg"], **prov)
            self.publish(wire.D_APPLY, {"seq": self.seq, "change_id": ch["id"], "gen": gen})
            return self.seq
        from arms.a.core import dispatch
        path = api.a_change_path(ch, self.arm_dir)
        targets = dispatch(self.bus, self.arm_dir, path, self.seq, ch["id"])
        self.log.write("dispatch", request_id=self.seq, change_id=ch["id"], path=path,
                       sha256=api.sha256_file(path), targets=targets)
        return [self.seq, targets]


def main():
    run_dir, name = os.environ["CS_RUN"], os.environ["CS_PROC"]
    with open(os.path.join(run_dir, "plan.json")) as f:
        arm = json.load(f)["arm"]
    cls = {"driver": Driver, "d-sm": DSM, "a-ltm": ALTM}.get(name) or (DAgents if arm == "d" else AAgents)
    p = cls(run_dir, name)
    try:
        p.run()
    except Exception as e:
        p.log.write("error", error=repr(e))
        raise


if __name__ == "__main__":
    main()
