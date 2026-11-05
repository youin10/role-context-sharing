"""Expected answers (docs/interfaces.md §5, §12.1), computed independently of the arms.

Inputs only: scenario.json, truth/cfg/<cfg>.yml (needs table + assignment) and the producer
trace. The YAML loader of rcs.model is reused (interfaces §1); condition evaluation and the
answer computation are implemented here.

Definitions (k = producer trace order, state k = events 0..k applied, k = -1 empty):
  E_v(a, k)     items x = (context, instance) that exist in state k, are read by some role of a
                in cfg v, and satisfy that role's `where` (OR over roles).
  deliver_to    a with x ∈ E_v(a, k), or e_k is a delete and x ∈ E_v(a, k-1);
                minus the producer of e_k (self-receipt excluded, brief §6 Q-S1: Sc ∖ sender).
  revoke_to     a with x ∈ E_v(a, k-1), x ∉ E_v(a, k) and e_k not a delete; minus the producer.
E does not depend on the producer, so transition notices / current values (§5.4) are state-based.
"""
from __future__ import annotations

import bisect
import json
import os
from collections import defaultdict
from dataclasses import dataclass, field

from rcs.model import Cfg, load_yaml

ORACLE_VERSION = "oracle-1.4 (2026-10-23, self-receipt excluded; gate: resync current values are redundant, Q-D3; transition notice window up to T_a + settle, REQ-3; lose-only agents up to the last apply_done + settle, §16; A2 event notices to agents paused at emission are deferred until the pause ends + settle, like A1; lost/gained sets optional over every state of the span; REQ-3 cond. 3 for required notices only)"
SELF_RECEIPT = False


def holds(where, value) -> bool:
    """Field-constant AND. `where`: list of {field, op, value} dicts or objects with those attrs."""
    if value is None:
        return False
    for c in where:
        f, op, const = (c["field"], c["op"], c["value"]) if isinstance(c, dict) else (c.field, c.op, c.value)
        if f not in value:
            return False
        v = value[f]
        if op == "=":
            ok = v == const
        elif op == "!=":
            ok = v != const
        elif op == "<":
            ok = v < const
        elif op == "<=":
            ok = v <= const
        elif op == ">":
            ok = v > const
        elif op == ">=":
            ok = v >= const
        else:
            raise ValueError(f"unknown operator {op}")
        if not ok:
            return False
    return True


@dataclass
class CfgReaders:
    """Per cfg: context -> {agent: [where, ...]} (one where-list per role of the agent reading it)."""
    cfg_id: str
    readers: dict = field(default_factory=lambda: defaultdict(dict))

    @staticmethod
    def of(cfg: Cfg):
        out = CfgReaders(cfg.cfg_id)
        roles = {r.name: r for r in cfg.needs.roles}
        for agent, rs in cfg.assignment.agents.items():
            for rn in rs:
                for rd in roles[rn].reads:
                    out.readers[rd.context].setdefault(agent, []).append(list(rd.where))
        return out

    def member(self, agent, context, value) -> bool:
        wheres = self.readers.get(context, {}).get(agent)
        return bool(wheres) and value is not None and any(holds(w, value) for w in wheres)

    def members(self, context, value) -> set:
        if value is None:
            return set()
        return {a for a, ws in self.readers.get(context, {}).items() if any(holds(w, value) for w in ws)}

    def conditional(self, agent, context) -> bool:
        """True if every role of `agent` reading `context` has a condition (a value can fall outside)."""
        ws = self.readers.get(context, {}).get(agent)
        return bool(ws) and all(ws)


@dataclass
class Event:
    k: int
    event_id: str
    t: float
    producer: str
    context: str
    instance: str
    op: str
    value: dict | None


class Oracle:
    """In-memory answers for one scenario. `prev[k]` / `vals[k]` = value of x_k in state k-1 / k."""

    def __init__(self, scenario_dir, self_receipt=SELF_RECEIPT):
        self.dir = scenario_dir
        with open(os.path.join(scenario_dir, "scenario.json")) as f:
            self.sc = json.load(f)
        files = self.sc["files"]
        self.cfg_ids = list(self.sc["cfgs"])
        self.cfgs = {c: Cfg.from_dict(load_yaml(os.path.join(scenario_dir, files["cfg_dir"], f"{c}.yml")))
                     for c in self.cfg_ids}
        self.readers = {c: CfgReaders.of(cfg) for c, cfg in self.cfgs.items()}
        with open(os.path.join(scenario_dir, files["producer"])) as f:
            self.events = [Event(**json.loads(line)) for line in f if line.strip()]
        for i, e in enumerate(self.events):
            assert e.k == i and e.event_id == f"e{i:06d}", (i, e.event_id)
        self.self_receipt = self_receipt
        self._replay()

    # replay ----------------------------------------------------------------------
    def _replay(self):
        state = {}
        self.prev, self.vals = [], []
        self.item_events = defaultdict(list)          # x -> [k, ...]
        self.last_producer = []                       # producer of the latest event on x_k (= e_k.producer)
        self.deliver_to = {c: [] for c in self.cfg_ids}
        self.revoke_to = {c: [] for c in self.cfg_ids}
        open_iv = {c: {} for c in self.cfg_ids}       # (agent, x) -> k_from
        self.intervals = {c: [] for c in self.cfg_ids}  # (agent, ctx, inst, k_from, k_to | None)
        for e in self.events:
            x = (e.context, e.instance)
            before = state.get(x)
            after = None if e.op == "delete" else dict(e.value)
            if after is None:
                state.pop(x, None)
            else:
                state[x] = after
            self.prev.append(before)
            self.vals.append(after)
            self.item_events[x].append(e.k)
            for c in self.cfg_ids:
                rd = self.readers[c]
                was, now = rd.members(e.context, before), rd.members(e.context, after)
                dl = set(now) | (was if e.op == "delete" else set())
                rv = (was - now) if e.op != "delete" else set()
                if not self.self_receipt:
                    dl.discard(e.producer)
                    rv = rv - {e.producer}
                self.deliver_to[c].append(dl)
                self.revoke_to[c].append(rv)
                for a in was - now:
                    k_from = open_iv[c].pop((a, x))
                    self.intervals[c].append((a, e.context, e.instance, k_from, e.k))
                for a in now - was:
                    open_iv[c][(a, x)] = e.k
        for c in self.cfg_ids:
            for (a, x), k_from in open_iv[c].items():
                self.intervals[c].append((a, x[0], x[1], k_from, None))
            self.intervals[c].sort(key=lambda r: (r[0], r[1], r[2], r[3]))
        self._index()

    def _index(self):
        self._elig = {}    # (cfg, agent) -> {x: [(k_from, k_to)]}
        for c in self.cfg_ids:
            for a, ctx, inst, k_from, k_to in self.intervals[c]:
                self._elig.setdefault((c, a), defaultdict(list))[(ctx, inst)].append(
                    (k_from, k_to if k_to is not None else 1 << 60))

    # queries ---------------------------------------------------------------------
    def eligible(self, cfg, agent, k) -> set:
        return {x for x, ivs in self._elig.get((cfg, agent), {}).items() if any(a <= k < b for a, b in ivs)}

    def is_eligible(self, cfg, agent, x, k) -> bool:
        return any(a <= k < b for a, b in self._elig.get((cfg, agent), {}).get(tuple(x), ()))

    def value_at(self, x, k):
        """Value of x in state k (None = absent) and the event id of the latest event on x (≤ k)."""
        ks = self.item_events.get(tuple(x), [])
        i = bisect.bisect_right(ks, k) - 1
        if i < 0:
            return None, None
        return self.vals[ks[i]], self.events[ks[i]].event_id

    def agents(self):
        return list(self.sc["agents"])

    # output (interfaces §12.1) ---------------------------------------------------
    def write(self, out_dir):
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "eligibility.jsonl"), "w") as f:
            for c in self.cfg_ids:
                for a, ctx, inst, k_from, k_to in self.intervals[c]:
                    f.write(json.dumps({"cfg": c, "agent": a, "context": ctx, "instance": inst,
                                        "k_from": k_from, "k_to": k_to}, ensure_ascii=False) + "\n")
        with open(os.path.join(out_dir, "deliveries.jsonl"), "w") as f:
            for c in self.cfg_ids:
                for e in self.events:
                    f.write(json.dumps({"cfg": c, "event_id": e.event_id, "k": e.k,
                                        "deliver_to": sorted(self.deliver_to[c][e.k]),
                                        "revoke_to": sorted(self.revoke_to[c][e.k])}) + "\n")
        meta = {"scenario_id": self.sc["scenario_id"], "cfgs": self.cfg_ids, "oracle_version": ORACLE_VERSION,
                "events": len(self.events), "self_receipt": self.self_receipt,
                "counts": {c: {"deliveries": sum(len(s) for s in self.deliver_to[c]),
                               "revokes": sum(len(s) for s in self.revoke_to[c]),
                               "intervals": len(self.intervals[c])} for c in self.cfg_ids}}
        with open(os.path.join(out_dir, "meta.json"), "w") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
        return meta
