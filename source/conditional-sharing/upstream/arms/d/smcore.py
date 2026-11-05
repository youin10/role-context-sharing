"""SM core (F2, F3) without ROS: a central current-value store that routes producer reports
by the installed sharing configuration and switches configurations atomically.

Run-time transition (F2):
  sequence   every configuration carries a sequence number; commits happen in order and a
             later one waits until the earlier one is committed (X1)
  staging    an incoming configuration is validated and held before it is committed
  boundary   reports are processed one at a time; a commit happens between two reports, so
             every report is routed wholly by the old or wholly by the new configuration
  atomic     the swap updates every agent at the same point of the report order
  revoke     items an agent loses get on_revoke; items it gains get the snapshot current value
  deadline   agents acknowledge the commit; missing acknowledgements after `deadline_s`
             are retransmitted until they arrive (X3) and the overrun is reported
  resync     a restarted SM sends every agent a snapshot of the current values it is eligible
             for, then a `sync` marker listing deleted items; the agent hands held deleted items
             over as deletions and revokes what else it holds outside the snapshot
             (latest-value convergence, brief §9 Q-D3). The SM node sends it only after the
             reports published while it was down have been replayed, so it is not stale.
             Agents that had not acknowledged a commit keep getting reports, until then, for the
             items they are eligible for under both the configuration they still run and the
             committed one; their transition batch (computed on the replayed store) precedes the
             snapshot and the commit marker follows it
Stale or duplicate reports are dropped by the producer instance version of the common
envelope (rcs.envelope.order_key), never by the global event order (brief §9 Q-D2).
Conditional sharing (F3): field–constant AND conditions evaluated on every report — entry
delivers, an update inside delivers, exit sends a notice. No agent is ever paused.
Self-receipt is excluded (recipients = Sc minus sender).

Outgoing messages are (agent, dict) pairs; per agent `m` increases by one and `inc` names
the SM incarnation, so agents can drop retransmitted duplicates.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from arms.d.spec import Cond
from rcs.envelope import newer, order_key

KINDS = ("deliver", "current", "revoke", "commit", "sync")


@dataclass
class Installed:
    gen: dict
    seq: int
    change_id: str | None
    index: dict = field(default_factory=dict)   # context -> [(agent, alts)]

    @staticmethod
    def of(gen, seq, change_id=None):
        inst = Installed(gen, seq, change_id)
        for agent, per in gen["consumers"].items():
            for c, alts in per.items():
                inst.index.setdefault(c, []).append((agent, [tuple(Cond(**x) for x in conj) for conj in alts]))
        return inst

    def alts(self, agent, context):
        for a, alts in self.index.get(context, []):
            if a == agent:
                return alts
        return None


def satisfied(alts, value):
    return value is not None and alts is not None and any(all(c.holds(value) for c in conj) for conj in alts)


class SMCore:
    def __init__(self, initial_gen, incarnation=1, journal=None, deadline_s=2.0, retransmit_s=0.5,
                 crash_hook=None):
        self.inc = incarnation
        self.journal = journal or (lambda rec: None)
        self.crash_hook = crash_hook or (lambda point: None)   # X2 fault injection (tests, D_CRASH_POINT)
        self.deadline_s, self.retransmit_s = deadline_s, retransmit_s
        self.active = Installed.of(initial_gen, 0)
        self.store = {}            # context -> {instance: (value, event_id)}
        self.tomb = {}             # context -> {instance: event_id of its deletion}
        self.hold = {}             # restart: agent -> configuration it still runs until the resync
        self.ver = {}              # (context, instance) -> order key of the last applied report
        self.staged = {}           # seq -> (gen, change_id)
        self.pending = {}          # seq -> {"agents": set, "t": commit time, "late": bool, "change_id"}
        self.batches = {}          # (seq, agent) -> [msg]
        self._m = {}               # agent -> last message number
        self.stats = {"reports": 0, "stale": 0, "deliver": 0, "current": 0, "revoke": 0, "retransmit": 0,
                      "outside_report_cfg": 0, "resync": 0}
        self.outside = []          # run-time finding: a write the producer report configuration lacks

    # messages ---------------------------------------------------------------------
    def _msg(self, agent, kind, **body):
        self._m[agent] = self._m.get(agent, 0) + 1
        m = {"m": self._m[agent], "inc": self.inc, "k": kind, **body}
        if kind == "revoke":
            m["n"] = f"{self.inc}-{agent}-{m['m']}"
        if kind in self.stats:
            self.stats[kind] += 1
        return agent, m

    # producer reports (F3 routing) ---------------------------------------------------
    def report(self, ev, journal=True):
        """ev: common envelope rcs-env/1 {event_id, producer, pv, context, instance, op, value}"""
        c, i, x = ev["context"], ev["instance"], (ev["context"], ev["instance"])
        if not newer(ev, self.ver.get(x)):
            self.stats["stale"] += 1
            return []
        if journal:
            self.journal({"r": ev})
        self.stats["reports"] += 1
        if c not in self.active.gen["producers"].get(ev["producer"], []):
            self.stats["outside_report_cfg"] += 1      # still routed: the store is the state of record
            if len(self.outside) < 100:
                self.outside.append((ev["event_id"], ev["producer"], c, self.active.seq))
        prev = self.store.get(c, {}).get(i)
        prev_val = prev[0] if prev else None
        new_val = ev["value"] if ev["op"] == "upsert" else None
        out = []
        routes = [(a, alts, None) for a, alts in self.active.index.get(c, []) if a not in self.hold]
        for a, inst in self.hold.items():
            alts = inst.alts(a, c)
            if alts is not None and self.active.alts(a, c) is not None:
                routes.append((a, alts, self.active.alts(a, c)))
        for agent, alts, alts2 in routes:
            if agent == ev["producer"]:
                continue
            was, now = satisfied(alts, prev_val), satisfied(alts, new_val)
            if alts2 is not None:        # held: only items it keeps under both configurations
                was, now = was and satisfied(alts2, prev_val), now and satisfied(alts2, new_val)
            if ev["op"] == "upsert":
                if now:
                    out.append(self._msg(agent, "deliver", c=c, i=i, v=new_val, e=ev["event_id"]))
                elif was:
                    out.append(self._msg(agent, "revoke", c=c, i=i, seq=self.active.seq))
            elif was:
                out.append(self._msg(agent, "deliver", c=c, i=i, v=None, e=ev["event_id"]))
        self.ver[x] = order_key(ev)
        if new_val is None:
            self.store.get(c, {}).pop(i, None)
            self.tomb.setdefault(c, {})[i] = ev["event_id"]
        else:
            self.store.setdefault(c, {})[i] = (new_val, ev["event_id"])
            self.tomb.get(c, {}).pop(i, None)
        return out

    # configuration transition (F2) -----------------------------------------------------
    def stage(self, seq, gen, change_id, now, journal=True):
        if seq <= self.active.seq or seq in self.staged:
            return []                                   # duplicate (replay after a restart)
        if gen.get("schema") != "rcs-d-gen/1":
            raise ValueError("not a generated configuration")
        self.staged[seq] = (gen, change_id)
        if journal:
            self.journal({"s": seq, "change_id": change_id, "gen": gen})
            self.crash_hook("after_stage")
        out = []
        while self.active.seq + 1 in self.staged:
            out += self._commit(self.active.seq + 1, now, journal)
        return out

    def _commit(self, seq, now, journal=True):
        gen, change_id = self.staged.pop(seq)
        old, new = self.active, Installed.of(gen, seq, change_id)
        agents = sorted(set(old.gen["agents"]) | set(new.gen["agents"]))
        out = []
        for a in agents:
            batch = self._diff(a, old, new, seq)
            batch.append(self._msg(a, "commit", seq=seq, cfg=gen["cfg"], change_id=change_id))
            self.batches[(seq, a)] = [m for _, m in batch]
            out += batch
        self.active = new
        self.pending[seq] = {"agents": set(agents), "t": now, "late": False, "change_id": change_id,
                             "last_tx": now, "cfg": gen["cfg"]}
        if journal:
            self.journal({"c": seq})
            self.crash_hook("after_commit")       # committed and journaled, nothing sent yet
        return out

    def _diff(self, a, old, new, seq):
        """Agent a's transition from `old` to `new` on the current store."""
        batch = []
        ctxs = set(old.gen["consumers"].get(a, {})) | set(new.gen["consumers"].get(a, {}))
        for c in sorted(ctxs):
            ao, an = old.alts(a, c), new.alts(a, c)
            for i, (val, eid) in sorted(self.store.get(c, {}).items()):
                was, now_ = satisfied(ao, val), satisfied(an, val)
                if now_ and not was:
                    batch.append(self._msg(a, "current", c=c, i=i, v=val, e=eid, seq=seq, tr=True))
                elif was and not now_:
                    batch.append(self._msg(a, "revoke", c=c, i=i, seq=seq, tr=True))
        return batch

    def ack(self, agent, seq, journal=True):
        """An agent applied every configuration up to `seq`. Returns [(seq, change_id)] completed."""
        done = []
        for s, p in sorted(self.pending.items()):
            if s <= seq and agent in p["agents"]:
                p["agents"].discard(agent)
                if journal:
                    self.journal({"a": agent, "seq": s})
                if not p["agents"]:
                    done.append((s, p["change_id"]))
        for s, _ in done:
            del self.pending[s]
            for key in [k for k in self.batches if k[0] == s]:
                del self.batches[key]
        return done

    def due(self, now):
        """Retransmissions and deadline overruns. Returns (messages, [(seq, change_id)] newly late)."""
        out, late = [], []
        for s, p in self.pending.items():
            if now - p["t"] < self.deadline_s:
                continue
            if not p["late"]:
                p["late"] = True
                late.append((s, p["change_id"]))
            if now - p["last_tx"] >= self.retransmit_s:
                p["last_tx"] = now
                for a in sorted(p["agents"]):
                    for m in self.batches.get((s, a), []):
                        out.append((a, m))
                        self.stats["retransmit"] += 1
        return out, late

    def snapshot(self, now=0.0):
        """Resync after a restart: every agent gets the current value of each item it is
        eligible for, then a `sync` marker with the deleted items of its contexts. A held agent
        first gets its transition from the configuration it still runs (on the replayed store)
        and, after the sync, the commit markers of the sequences it owes."""
        out = []
        for a in sorted(set(self.active.gen["agents"]) | set(self.hold)):
            batch = self._diff(a, self.hold[a], self.active, self.active.seq) if a in self.hold else []
            ctxs = sorted(self.active.gen["consumers"].get(a, {}))
            for c in ctxs:
                alts = self.active.alts(a, c)
                for i, (val, eid) in sorted(self.store.get(c, {}).items()):
                    if satisfied(alts, val):
                        batch.append(self._msg(a, "current", c=c, i=i, v=val, e=eid, rs=True))
                        self.stats["resync"] += 1
            dels = [[c, i, e] for c in ctxs for i, e in sorted(self.tomb.get(c, {}).items())]
            batch.append(self._msg(a, "sync", seq=self.active.seq, dels=dels))
            if a in self.hold:
                for s, p in sorted(self.pending.items()):
                    if a in p["agents"]:
                        batch.append(self._msg(a, "commit", seq=s, cfg=p["cfg"], change_id=p["change_id"]))
                        self.batches[(s, a)] = [m for _, m in batch]
                        p["t"] = p["last_tx"] = now
            out += batch
        self.hold = {}
        return out

    # restart (X2) ----------------------------------------------------------------------------
    @staticmethod
    def recover(initial_gen, records, incarnation, journal, now, **kw):
        """Rebuild from the journal: reports -> store, staged/committed configurations -> active
        configuration and pending acknowledgements. Committed-but-unacknowledged agents get a
        staged-only ones are committed. Unacknowledged agents are held on the configuration
        before their first pending sequence (routed by its intersection with the committed one)
        until the caller sends snapshot() once the missed reports have been replayed.
        Returns (core, messages to send now)."""
        sm = SMCore(initial_gen, incarnation, journal, **kw)
        gens, committed, acks = {}, [], {}
        for r in records:
            if "r" in r:
                sm.report(r["r"], journal=False)
            elif "s" in r:
                gens[r["s"]] = (r["gen"], r["change_id"])
            elif "c" in r:
                committed.append(r["c"])
            elif "a" in r:
                acks.setdefault(r["seq"], set()).add(r["a"])
        out = []
        before = {}
        for s in sorted(committed):
            gen, cid = gens[s]
            sm.staged[s] = (gen, cid)
            before[s] = sm.active
            sm._commit(s, now, journal=False)
            p = sm.pending[s]
            p["agents"] -= acks.get(s, set())
            if not p["agents"]:
                del sm.pending[s]
        for s in sorted(k for k in gens if k not in committed):
            before.setdefault(s, sm.active)
            sm.stage(s, gens[s][0], gens[s][1], now, journal=True)
        sm.batches = {}
        sm._m = {}                               # numbers of the new incarnation start at 1
        sm.stats = {k: 0 for k in sm.stats}
        for s_, p in sorted(sm.pending.items(), reverse=True):
            for a in p["agents"]:
                sm.hold[a] = before[s_]          # the earliest pending sequence it owes wins
        return sm, out


class AgentCore:
    """Agent-side handling of SM messages (no ROS). Drops duplicates (same incarnation, m not
    increasing) and transition messages (`tr`) of a sequence it already applied; returns the
    application calls to make and the sequence to acknowledge, if any. Tracks the items it
    holds so a resync (`rs` current values + `sync`) can revoke what the snapshot lacks."""

    def __init__(self):
        self.last_m = {}        # incarnation -> last m
        self.applied_seq = 0
        self.dups = 0
        self.gaps = 0           # messages skipped inside one incarnation (diagnostic; should stay 0)
        self.held = set()       # (context, instance) handed to the application and not withdrawn
        self.own = set()        # items self-written since their last SM delivery
        self.synced = {}        # incarnation -> items in its snapshot
        self.resync_revokes = 0
        self.revokes_not_held = 0

    def self_write(self, context, instance):
        """The agent's own write replaces whatever the SM gave it for that item (self-receipt
        is excluded, so no SM message follows); a later resync must not revoke it."""
        self.held.discard((context, instance))
        self.own.add((context, instance))

    def handle(self, msg):
        inc, m = msg["inc"], msg["m"]
        if m <= self.last_m.get(inc, 0):
            self.dups += 1
            return [], None
        if m > self.last_m.get(inc, 0) + 1:
            self.gaps += m - self.last_m.get(inc, 0) - 1
        self.last_m[inc] = m
        k = msg["k"]
        if k == "commit":
            self.applied_seq = max(self.applied_seq, msg["seq"])
            return [], self.applied_seq
        if k == "sync":
            calls = []
            for c, i, e in msg.get("dels", []):
                if (c, i) in self.held:
                    self.held.discard((c, i))
                    calls.append(("on_deliver", c, i, None, e))
            gone = sorted(self.held - self.synced.pop(inc, set()))
            self.held -= set(gone)
            self.resync_revokes += len(gone)
            return calls + [("on_revoke", c, i, f"{inc}-sync-{m}-{n}") for n, (c, i) in enumerate(gone)], None
        if msg.get("tr") and msg["seq"] <= self.applied_seq:
            return [], None                     # transition already applied (SM restart resend)
        x = (msg["c"], msg["i"])
        if k == "deliver":
            self.own.discard(x)
            (self.held.add if msg["v"] is not None else self.held.discard)(x)
            return [("on_deliver", msg["c"], msg["i"], msg["v"], msg["e"])], None
        if k == "current":
            self.own.discard(x)
            self.held.add(x)
            if msg.get("rs"):
                self.synced.setdefault(inc, set()).add(x)
            return [("on_current_value", msg["c"], msg["i"], msg["v"], msg["e"])], None
        if k == "revoke":
            if x not in self.held and x not in self.own:
                self.revokes_not_held += 1
                return [], None
            self.held.discard(x)
            return [("on_revoke", msg["c"], msg["i"], msg["n"])], None
        raise ValueError(k)
