"""Baseline A without ROS: the LTM of arms/a/ltm.py and the agent of arms/a/agent.py with the
rclpy publishers replaced by an in-process FIFO bus (core experiment, conditional-sharing).

The request / notification logic is copied from the two node classes at rcs-experiments
7bef3ecd (see ../../../patches/a-core.diff for the line-by-line difference). Changes:
  - String publishers -> Bus.send(destination, dict); the in-process bus delivers every message
    in global send order. This is a property of this core harness only; it is not a claim about
    the ordering a ROS 2 / DDS deployment provides (that is measured separately in live/);
  - field order comes from the ontology argument order (fields_from_signature) instead of the
    scenario's public needs.md table (same order: key, then the value fields);
  - plans are read from a directory given by the caller; logging goes to a list.
No behaviour of the rules, exit watches, tombstones or exit notices was changed. Application
callbacks use the consumer knowledge notifications: a fact the agent does not hold yet is
asserted, a held fact whose new value is accepted is updated, and a held fact that is deleted,
leaves the conditions or loses its rules is retracted. LTM operation names (assert / update /
retract reports, subscribe, notify, match) are those of the original framework.
"""
from __future__ import annotations

import os
from collections import deque

import yaml

from arms.a import gl
from rcs.envelope import order_key


class Bus:
    def __init__(self):
        self.q = deque()
        self.nodes = {}
        self.sent = 0

    def send(self, dest, d):
        self.q.append((dest, d))
        self.sent += 1

    def pump(self, limit=100000):
        n = 0
        while self.q:
            dest, d = self.q.popleft()
            self.nodes[dest].receive(d)
            n += 1
            if n > limit:
                raise RuntimeError("bus did not settle")
        return n


def key_of(fact):
    return fact[0].name, gl.fmt(fact[1]) if len(fact) > 1 else ""


def fields_from_signature(signature):
    """{context: [value field, ...]} in argument order (ontology argumentIndex 1..n)."""
    return {c: list(s["fields"]) for c, s in signature.items()}


class LTMCore:
    """arms/a/ltm.py LTM._on_req without rclpy."""

    def __init__(self, bus):
        self.bus = bus
        self.latest = {}
        self.record = {}
        self.subs = {}
        self.counts = {"notify": 0, "match": 0, "assert": 0}
        bus.nodes["ltm"] = self

    def _send(self, agent, d):
        self.bus.send(agent, d)

    def receive(self, d):
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


def load_rules(plans_dir, roles):
    """{context: [Rule]} of the agent's roles, union over roles (copied from arms/a/agent.py)."""
    out = {}
    for r in roles:
        with open(os.path.join(plans_dir, f"{r}.yml")) as f:
            doc = yaml.safe_load(f) or {}
        for text in doc.get("subscribe", []):
            rule = gl.Rule.parse(text)
            if rule.text not in [x.text for x in out.get(rule.context, [])]:
                out.setdefault(rule.context, []).append(rule)
    return out


class AAgentCore:
    """arms/a/agent.py AAgent without rclpy (variant a; asis=True gives variant A-asis)."""

    def __init__(self, agent, bus, app, order, arm_dir, asis=False):
        self.agent, self.bus, self.app, self.order, self.arm_dir = agent, bus, app, order, arm_dir
        self.asis = asis
        self.rules, self.subs, self.tomb, self.watch = {}, {}, {}, {}
        self.cache, self.held = {}, set()
        self.pending, self.buffer = {}, {}
        self.applied, self.ack_due = None, None
        self.n_sub = self.n_req = self.n_notice = 0
        self.skipped_deletes = 0
        self.written = set()
        self.acks = []
        self.log = []
        bus.nodes[agent] = self

    # producer -------------------------------------------------------------------------------
    def emit(self, env):
        x = (env["context"], env["instance"])
        if env["op"] == "delete":
            if self.asis:
                self.skipped_deletes += 1
                return
            fact = gl.tombstone_of(env["context"], env["instance"])
        else:
            fact = gl.fact_of(self.order, env["context"], env["instance"], env["value"])
        op = "update" if x in self.written else "assert"
        self.written.add(x)
        self._ltm(op, gl=gl.fmt(fact), env=env)

    def _ltm(self, op, **kw):
        self.bus.send("ltm", {"op": op, "agent": self.agent, **kw})

    # subscriptions ----------------------------------------------------------------------------
    def _subscribe(self, rule):
        self.n_sub += 1
        sub = f"{self.agent}-s{self.n_sub}"
        self._ltm("subscribe", sub=sub, rule=rule.text)
        return sub

    def _match(self, context, patterns):
        self.n_req += 1
        req = f"{self.agent}-m{self.n_req}"
        self.pending[req] = context
        self.buffer.setdefault(context, [])
        self._ltm("match", req=req, patterns=patterns)

    def _pattern(self, context, instance=None):
        n = len(self.order[context])
        key = gl.fmt(instance) if instance is not None else "$key"
        return f"({context} {key} " + " ".join(f"$v{i}" for i in range(n)) + ")"

    def _conditional_only(self, context):
        return all(r.conds for r in self.rules.get(context, []))

    # judgement --------------------------------------------------------------------------------
    def _deleted(self, env):
        return env["op"] == "delete"

    def _accepts(self, env):
        if self._deleted(env) or env["context"] not in self.rules:
            return False
        fact = gl.fact_of(self.order, env["context"], env["instance"], env["value"])
        return any(r.bind(fact) is not None for r in self.rules[env["context"]])

    def _newer(self, env):
        cur = self.cache.get((env["context"], env["instance"]))
        return cur is None or order_key(cur) < order_key(env)

    def _sample(self, env):
        if self._newer(env):
            self.cache[(env["context"], env["instance"])] = env
            self._judge(env, current=False)

    def _judge(self, env, current):
        x = (env["context"], env["instance"])
        own = env["producer"] == self.agent
        if self._accepts(env):
            gained = x not in self.held
            self.held.add(x)
            self._ensure_watch(x)
            if current and gained:
                self.app.on_assert(x[0], x[1], env["value"], env["event_id"])
            elif not current and not own:
                (self.app.on_assert if gained else self.app.on_update)(x[0], x[1], env["value"], env["event_id"])
        elif x in self.held:
            self.held.discard(x)
            self._drop_watch(x)
            if self._deleted(env):
                if not own:
                    self.app.on_retract(x[0], x[1], env["event_id"])
            elif not self.asis and not (own and not current):
                self._notice(x)

    def _notice(self, x):
        self.n_notice += 1
        self.app.on_retract(x[0], x[1], f"{self.agent}-a{self.n_notice}")

    def _ensure_watch(self, x):
        if self.asis or x in self.watch or not self._conditional_only(x[0]):
            return
        self.watch[x] = self._subscribe(self.rules[x[0]][0].for_instance(x[1]))
        self._match(x[0], [self._pattern(x[0], x[1]), gl.fmt(gl.tombstone_of(*x))])

    def _drop_watch(self, x):
        sub = self.watch.pop(x, None)
        if sub:
            self._ltm("unsubscribe", sub=sub)

    # inbox ------------------------------------------------------------------------------------
    def receive(self, d):
        if d["type"] == "notify":
            env = d["env"]
            if env["context"] in self.buffer:
                self.buffer[env["context"]].append(env)
            else:
                self._sample(env)
        elif d["type"] == "match":
            self._on_match(d)
        elif d["type"] == "load":
            if self.applied is not None and d["request_id"] <= self.applied["request_id"]:
                self._ack(self.applied)
            else:
                self._load(d)

    def _on_match(self, d):
        context = self.pending.pop(d["req"], None)
        if context is None:
            return
        found = {}
        for res in d["results"]:
            for r in res:
                env = r["env"]
                x = (env["context"], env["instance"])
                if x not in found or order_key(found[x]) < order_key(env):
                    found[x] = env
        if context in self.rules:
            for x, env in sorted(found.items()):
                if not self._newer(env):
                    env = self.cache[x]
                self.cache[x] = env
                self._judge(env, current=True)
        if context not in self.pending.values():
            for env in self.buffer.pop(context, []):
                self._sample(env)
        self._maybe_ack()

    # reorganisation (load the changed role plans) ---------------------------------------------
    def _load(self, target):
        plans = os.path.join(self.arm_dir, target["plans"])
        new = load_rules(plans, target["roles"])
        old_texts = {r.text for rs in self.rules.values() for r in rs}
        new_texts = {r.text for rs in new.values() for r in rs}
        changed = {c for c in set(self.rules) | set(new)
                   if {r.text for r in self.rules.get(c, [])} != {r.text for r in new.get(c, [])}}
        for text in sorted(old_texts - new_texts):
            self._ltm("unsubscribe", sub=self.subs.pop(text))
        self.rules = new
        for c in sorted(changed):
            if c not in new:
                if c in self.tomb:
                    self._ltm("unsubscribe", sub=self.tomb.pop(c))
                for x in sorted(x for x in self.held if x[0] == c):
                    self.held.discard(x)
                    self._drop_watch(x)
                    if not self.asis:
                        self._notice(x)
                self.buffer.pop(c, None)
        for c in sorted(changed & set(new)):
            for r in new[c]:
                if r.text not in self.subs:
                    self.subs[r.text] = self._subscribe(r)
            if not self.asis and c not in self.tomb:
                self.tomb[c] = self._subscribe(gl.tombstone_rule(c))
            if not self._conditional_only(c):
                for x in [x for x in self.watch if x[0] == c]:
                    self._drop_watch(x)
            self._match(c, [self._pattern(c)] + ([] if self.asis else [f"(deleted ({c} $key))"]))
        self.applied = target
        self.log.append({"name": "a_load", "request_id": target["request_id"], "roles": target["roles"],
                         "plans": target["plans"], "changed": sorted(changed)})
        if target["request_id"]:
            self.ack_due = target
            self._maybe_ack()

    def _maybe_ack(self):
        if self.ack_due is not None and not self.pending:
            self._ack(self.ack_due)
            self.ack_due = None

    def _ack(self, target):
        self.acks.append({"request_id": target["request_id"], "cfg": target["cfg"]})


def dispatch(bus, arm_dir, change_path, request_id, cfg):
    """arms/a/applier.py ADispatcher._begin + one send per target (no retries needed in-process)."""
    with open(change_path) as f:
        prep = yaml.safe_load(f)
    for a, t in prep["targets"].items():
        bus.send(a, {"type": "load", "request_id": request_id, "change_id": os.path.basename(change_path)[:-4],
                     "cfg": cfg, "roles": list(t["roles"]), "plans": t.get("plans", prep["plans"])})
    return sorted(prep["targets"])
