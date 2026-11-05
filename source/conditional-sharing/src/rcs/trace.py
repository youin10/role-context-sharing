"""Common trace formats: producer events and task requests (docs/interfaces.md §5).

Both traces are generated once per scenario and shared by the three arms. Event IDs
(`e000123`) are the common version IDs of producer events; `k` is the event's position
in the global order and indexes the store state "after event k".
"""
from __future__ import annotations

import heapq
import json
from dataclasses import asdict, dataclass

from rcs.timeline import CfgTimeline


@dataclass
class Event:
    k: int
    event_id: str
    t: float               # seconds after the run origin t0
    producer: str          # agent that emits it
    context: str
    instance: str
    op: str                # "upsert" | "delete"
    value: dict | None     # None for delete


@dataclass
class Task:
    task_id: str
    t: float
    agent: str
    role: str
    kind: str
    params: dict
    inputs: list           # [[context, instance], ...]
    deadline: float        # absolute seconds after t0


def write_jsonl(rows, path):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(asdict(r) if hasattr(r, "__dataclass_fields__") else r,
                               ensure_ascii=False, sort_keys=False) + "\n")


def read_events(path):
    with open(path) as f:
        return [Event(**json.loads(line)) for line in f if line.strip()]


def read_tasks(path):
    with open(path) as f:
        return [Task(**json.loads(line)) for line in f if line.strip()]


class TraceBuilder:
    """Discrete-event helper shared by the domain simulations."""

    def __init__(self, timeline: CfgTimeline, duration_s: float, mute=None):
        """mute: reporter absence (plan v2 §2.7) {"target", "contexts", "start_s", "duration_s"} —
        the target writes nothing to those contexts in [start, start + duration); its state
        keeps evolving, so the first write after the absence carries the then-current value."""
        self.mute = mute
        self.tl = timeline
        self.duration = duration_s
        self.state: dict[tuple[str, str], dict] = {}
        self._heap = []
        self._seq = 0
        self._events = []
        self._tasks = []
        self._rr: dict[str, int] = {}

    # scheduling -------------------------------------------------------------
    def at(self, t, fn, *args):
        if t < self.duration:
            heapq.heappush(self._heap, (round(t, 4), self._seq, fn, args))
            self._seq += 1

    def run(self):
        while self._heap:
            t, _, fn, args = heapq.heappop(self._heap)
            fn(t, *args)

    def run_until(self, t):
        """Execute callbacks due at or before t, leaving later callbacks queued."""
        while self._heap and self._heap[0][0] <= t:
            when, _, fn, args = heapq.heappop(self._heap)
            fn(when, *args)

    # producer events --------------------------------------------------------
    def emit(self, t, producer, context, instance, value):
        """Record a write if `producer` may change `context` at t (truth timeline); else drop it."""
        if producer is None or not self.tl.may_change(producer, context, t):
            return False
        m = self.mute
        if m and producer == m["target"] and context in m["contexts"] and \
                m["start_s"] <= t < m["start_s"] + m["duration_s"]:
            return False
        key = (context, instance)
        if value is None:
            if key not in self.state:
                return False
            del self.state[key]
        else:
            self.state[key] = dict(value)
        self._events.append((round(t, 4), len(self._events), producer, context, instance,
                             "delete" if value is None else "upsert", None if value is None else dict(value)))
        return True

    def pick(self, t, role, key=None):
        """Round-robin over agents bound to `role` at t (truth)."""
        agents = self.tl.at(t).assignment.agents_of(role)
        if not agents:
            return None
        rk = key or role
        i = self._rr.get(rk, 0)
        self._rr[rk] = i + 1
        return agents[i % len(agents)]

    # tasks ------------------------------------------------------------------
    def task(self, t, step, params, agent=None):
        """Issue the first task kind of `step` whose input contexts its role reads at t."""
        cfg = self.tl.at(t)
        for tk in (x for x in cfg.needs.tasks if x.step == step):
            role = cfg.needs.role(tk.role)
            if not all(role.read_of(c) for c, _ in tk.inputs):
                continue
            if agent is not None and tk.role not in cfg.assignment.agents.get(agent, []):
                continue        # an alternative of the same step may belong to the agent's other role
            target = agent if agent is not None else self.pick(t, tk.role, key="task:" + tk.role)
            if target is None:
                return None
            self._tasks.append((round(t, 4), target, tk.role, tk.kind, dict(params),
                                [[c, params[p]] for c, p in tk.inputs], round(t + tk.deadline_s, 4)))
            return target
        return None

    # output -----------------------------------------------------------------
    def finish(self):
        self.run()
        return self.collect()

    def collect(self):
        """Convert the recorded events and tasks without running queued callbacks."""
        evs = sorted(self._events, key=lambda e: (e[0], e[1]))
        events = [Event(k, f"e{k:06d}", e[0], e[2], e[3], e[4], e[5], e[6]) for k, e in enumerate(evs)]
        tks = sorted(self._tasks, key=lambda x: x[0])
        tasks = [Task(f"t{i:05d}", *x) for i, x in enumerate(tks)]
        return events, tasks
