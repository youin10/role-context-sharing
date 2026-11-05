"""Baseline A agent (spec 비교군 A): ARBI-style agent with role plans and LTM rule subscriptions.

  python3 -m arms.a.agent            (RCS_VARIANT = a | asis)

A role plan (plans/<rev>/<Role>.yml: role, subscribe: [rule, ...]) is written by a person; the
agent loads the plans of its roles (A-2-1), subscribes their rules and queries current values with
`match` right after subscribing (A-2-3). Reorganisation = loading the changed role plans at run
time (dispatcher load / parse / assert / execute, thesis table 15). Node-side helper library
(one-time cost, variant A only):
  - exit detection: a rule with conditions does not notify when a value leaves them (A-2-2), so
    while an item is held through conditional rules only, the agent watches that instance with
    the same pattern fixed to its key (subscribe, then match, so no update is missed);
  - deletion: producers assert the tombstone (deleted (<Ctx> "<id>")); the agent subscribes the
    tombstone rule of every context it reads and hands a held item's deletion to the application;
  - revoke notices for items lost by an unsubscribe or by a changed rule (A-2-4).
Variant A-asis (author's practice, A-2-4): facts only accumulate; no tombstone, no exit watch, no
revoke notices. Its gate results are motivation evidence only (brief §18-4).
Ordering: rcs-env/1 order keys; older samples are dropped. Self-receipt is excluded.
"""
from __future__ import annotations

import os

import yaml
from rclpy.node import Node
from std_msgs.msg import String

from arms.a import gl, wire
from rcs.envelope import envelope, order_key
from rcs.rosproc import main_agent


def load_rules(plans_dir, roles):
    """{context: [Rule]} of the agent's roles, union over roles (multi-role, M-2-5 likewise)."""
    out = {}
    for r in roles:
        with open(os.path.join(plans_dir, f"{r}.yml")) as f:
            doc = yaml.safe_load(f) or {}
        for text in doc.get("subscribe", []):
            rule = gl.Rule.parse(text)
            if rule.text not in [x.text for x in out.get(rule.context, [])]:
                out.setdefault(rule.context, []).append(rule)
    return out


class AAgent(Node):
    def __init__(self, ctx):
        super().__init__("a_" + ctx.agent)
        self.ctx, self.app, self.log, self.agent = ctx, ctx.app, ctx.log, ctx.agent
        self.asis = ctx.variant == "asis"
        self.order = gl.field_order(ctx.scenario_dir)
        base = os.path.join(ctx.arm_dir, ctx.scenario["scenario_id"])
        with open(os.path.join(base, "initial.yml")) as f:
            doc = yaml.safe_load(f)
        self.initial = {"request_id": 0, "cfg": ctx.scenario["initial_cfg"],
                        "roles": doc["agents"].get(ctx.agent, []), "plans": doc["plans"]}
        self.rules = {}              # context -> [Rule]
        self.subs = {}               # rule text -> sub id
        self.tomb = {}               # context -> sub id
        self.watch = {}              # (context, instance) -> sub id
        self.cache = {}              # (context, instance) -> env (latest seen)
        self.held = set()
        self.pending = {}            # req id -> context (match in flight)
        self.buffer = {}             # context -> [env] notifications while its match is in flight
        self.applied, self.ack_due = None, None
        self.n_sub = self.n_req = self.n_notice = 0
        self.skipped_deletes = 0
        self.written = set()
        self.req = self.create_publisher(String, wire.LTM, wire.QOS)
        self.ack = self.create_publisher(String, wire.ACK, wire.QOS)
        self.create_subscription(String, wire.inbox(ctx.agent), self._on_inbox, wire.QOS)

    def on_start(self):
        self._load(self.initial)     # after the warm-up: the LTM is discovered

    # producer -------------------------------------------------------------------------------
    def emit(self, e):
        env = envelope(e)
        x = (e.context, e.instance)
        if e.op == "delete":
            if self.asis:
                self.skipped_deletes += 1           # nothing marks a fact invalid (A-2-4)
                return
            fact = gl.tombstone_of(e.context, e.instance)
        else:
            fact = gl.fact_of(self.order, e.context, e.instance, e.value)
        op = "update" if x in self.written else "assert"
        self.written.add(x)
        self._ltm(op, gl=gl.fmt(fact), env=env)

    def _ltm(self, op, **kw):
        self.req.publish(String(data=wire.dumps({"op": op, "agent": self.agent, **kw})))

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
        """A notified fact: deliver, hand over a deletion, or notice an exit."""
        if self._newer(env):
            self.cache[(env["context"], env["instance"])] = env
            self._judge(env, current=False)

    def _judge(self, env, current):
        """current=True: the state after a match (current value for a gained item).
        Own writes update the held set only (self-receipt excluded); current values are
        state-based and include own values (interfaces §5.4)."""
        x = (env["context"], env["instance"])
        own = env["producer"] == self.agent
        if self._accepts(env):
            gained = x not in self.held
            self.held.add(x)
            self._ensure_watch(x)
            if current and gained:
                self.app.on_current_value(x[0], x[1], env["value"], env["event_id"])
            elif not current and not own:
                self.app.on_deliver(x[0], x[1], env["value"], env["event_id"])
        elif x in self.held:
            self.held.discard(x)
            self._drop_watch(x)
            if self._deleted(env):
                if not own:
                    self.app.on_deliver(x[0], x[1], None, env["event_id"])
            elif not self.asis and not (own and not current):
                self._notice(x)

    def _notice(self, x):
        self.n_notice += 1
        self.app.on_revoke(x[0], x[1], f"{self.agent}-a{self.n_notice}")

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
    def _on_inbox(self, msg):
        d = wire.loads(msg.data)
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
                self._ack(self.applied)               # idempotent re-apply
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
        plans = os.path.join(self.ctx.arm_dir, target["plans"])
        new = load_rules(plans, target["roles"])
        old_texts = {r.text for rs in self.rules.values() for r in rs}
        new_texts = {r.text for rs in new.values() for r in rs}
        changed = {c for c in set(self.rules) | set(new)
                   if {r.text for r in self.rules.get(c, [])} != {r.text for r in new.get(c, [])}}
        for text in sorted(old_texts - new_texts):
            self._ltm("unsubscribe", sub=self.subs.pop(text))
        self.rules = new
        for c in sorted(changed):
            if c not in new:                           # context no longer read: lost items
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
            if not self._conditional_only(c):        # every update arrives anyway: no watches
                for x in [x for x in self.watch if x[0] == c]:
                    self._drop_watch(x)
            self._match(c, [self._pattern(c)] + ([] if self.asis else [f"(deleted ({c} $key))"]))
        self.applied = target
        self.log.write("arm", name="a_load", request_id=target["request_id"], roles=target["roles"],
                       plans=target["plans"], changed=sorted(changed))
        if target["request_id"]:
            self.ack_due = target
            self._maybe_ack()

    def _maybe_ack(self):
        if self.ack_due is not None and not self.pending:
            self._ack(self.ack_due)
            self.ack_due = None

    def _ack(self, target):
        self.ack.publish(String(data=wire.dumps({"agent": self.agent, "request_id": target["request_id"],
                                                 "cfg": target["cfg"]})))
        if self.log.clock.known:
            self.log.write("ack", change_id=target.get("change_id"), cfg=target["cfg"],
                           request_id=target["request_id"])

    def shutdown(self):
        if self.log.clock.known:
            self.log.write("arm", name="a_agent_counts", subscriptions=self.n_sub, matches=self.n_req,
                           watches=len(self.watch), skipped_deletes=self.skipped_deletes)


def make_node(ctx):
    return AAgent(ctx)


if __name__ == "__main__":
    main_agent(make_node)
