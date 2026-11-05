"""Baseline A: the central LTM (spec 비교군 A, A-1; ARBI README "LTM Interface", thesis table 4).

  python3 -m arms.a.ltm              (main_service, a process next to the agents like D's SM)

Requests on wire.LTM (JSON): {op, agent, ...}
  assert / update   {gl, env}         store the fact as the latest of its key and append it to the
                                      record; notify every subscription whose rule matches
  retract           {gl}              remove the latest fact of the key (no notification, README)
  match             {req, patterns}   latest facts that unify with each pattern
  subscribe         {sub, rule}       register (the subscription ID is proposed by the agent so
                                      that a reply is not needed over the asynchronous link)
  unsubscribe       {sub}
The key of a fact is (name, first argument). The LTM knows no context semantics: deletion is a
tombstone fact like any other (A-2-4); it notifies on assert and update only (README).
Writes overwrite the key's latest value in arrival order, as the Redis store does.
"""
from __future__ import annotations

from rclpy.node import Node
from std_msgs.msg import String

from arms.a import gl, wire
from rcs.rosproc import main_service


def key_of(fact):
    return fact[0].name, gl.fmt(fact[1]) if len(fact) > 1 else ""


class LTM(Node):
    def __init__(self, ctx):
        super().__init__("a_ltm")
        self.log = ctx.log
        self.latest = {}             # key -> (fact, gl text, env)
        self.record = {}             # key -> number of facts stored so far (cumulative record)
        self.subs = {}               # sub id -> (agent, Rule)
        self.out = {a: self.create_publisher(String, wire.inbox(a), wire.QOS) for a in ctx.scenario["agents"]}
        self.counts = {"notify": 0, "match": 0, "assert": 0}
        self.create_subscription(String, wire.LTM, self._on_req, wire.QOS)

    def _send(self, agent, d):
        self.out[agent].publish(String(data=wire.dumps(d)))

    def _on_req(self, msg):
        d = wire.loads(msg.data)
        op = d["op"]
        if op in ("assert", "update"):
            fact = gl.parse(d["gl"])
            k = key_of(fact)
            self.latest[k] = (fact, d["gl"], d.get("env"))
            self.record[k] = self.record.get(k, 0) + 1
            self.counts["assert"] += 1
            for sub, (agent, rule) in list(self.subs.items()):
                b = rule.bind(fact)
                if b is not None:
                    self.counts["notify"] += 1
                    self._send(agent, {"type": "notify", "sub": sub, "gl": rule.notification(b), "env": d.get("env")})
        elif op == "retract":
            self.latest.pop(key_of(gl.parse(d["gl"])), None)
        elif op == "match":
            self.counts["match"] += 1
            res = []
            for p in d["patterns"]:
                pat = gl.parse(p)
                res.append([{"gl": text, "env": env} for fact, text, env in self.latest.values()
                            if gl.unify(pat, fact, {}) is not None])
            self._send(d["agent"], {"type": "match", "req": d["req"], "results": res})
        elif op == "subscribe":
            self.subs[d["sub"]] = (d["agent"], gl.Rule.parse(d["rule"]))
        elif op == "unsubscribe":
            self.subs.pop(d["sub"], None)

    def shutdown(self):
        if self.log.clock.known:
            self.log.write("arm", name="a_ltm_counts", keys=len(self.latest), subs=len(self.subs), **self.counts)


if __name__ == "__main__":
    main_service(LTM)
