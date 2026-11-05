"""Common application interface and the shared decision application (spec §0.4).

Arms deliver to the application only through ContextApp:
  on_current_value(context, instance, value, event_id)  — first, for every newly received item
  on_deliver(context, instance, value, event_id)        — producer events; value None = deleted
  on_revoke(context, instance, notice_id)               — last, for every item no longer received
plus set_paused(True/False) when the arm stops delivery to the application (M-lc gate,
R adaptation state). The decision rule is the same code for every arm.

Self-receipt is excluded (recipients = Sc minus sender): an arm never delivers an agent's own
events back to it. The harness writes the agent's own writes into its view instead
(on_self_write), identically for every arm.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rcs.log import EventLog
from rcs.trace import Task


class ContextApp:
    """The interface an arm adapter calls. Subclasses implement the three callbacks."""

    def on_deliver(self, context: str, instance: str, value: dict | None, event_id: str) -> None:
        raise NotImplementedError

    def on_revoke(self, context: str, instance: str, notice_id: str) -> None:
        raise NotImplementedError

    def on_current_value(self, context: str, instance: str, value: dict, event_id: str) -> None:
        raise NotImplementedError

    def set_paused(self, paused: bool, reason: str = "") -> None:
        raise NotImplementedError


# Value-based decision functions (docs/interfaces.md §19, experiment plan v2 §2.2). One per task
# kind; the input values arrive in the task's input order. The oracle computes the correct
# decision independently from the same table.
NODE_ZONE = {"dock-in": "inbound", "aisle-in": "inbound", "inspect": "inspection", "aisle-insp": "inspection",
             "bay": "storage", "dock-out": "outbound", "aisle-out": "outbound"}


def node_zone(node):
    base = node.rsplit("-", 1)[0] if node.rsplit("-", 1)[-1].isdigit() else node
    return NODE_ZONE.get(base, "unknown")


def _bay_dock(node):
    n = node.rsplit("-", 1)[-1]
    return "dock-out-1" if not node.startswith("bay-") or int(n) <= 6 else "dock-out-2"


DECISIONS = {
    "admit": lambda c: "urgent" if c["priority"] == "urgent" else ("heavy" if c["weight"] >= 30 else "normal"),
    "pickup": lambda c: "lift-heavy" if c["weight"] >= 30 else "lift",
    "stow-by-verdict": lambda s, _carried: "general-bay" if s["status"] == "pass" else "quarantine-bay",
    "stow": lambda _carried: "general-bay",
    "review": lambda s: "confirm" if s["status"] == "pass" else "re-inspect",
    "dispatch-pick": lambda c, _stored: "pick-now" if c["priority"] == "urgent" else "pick-queued",
    "ship": lambda _c, stored: _bay_dock(stored["node"]),
    "battery-check": lambda r: "exclude" if r["battery"] < 20 else "keep",
    "route": lambda loc: "route-" + node_zone(loc["node"]),
    "move": lambda z: "wait" if z["access"] == "blocked" else ("slow" if z["congestion"] >= 3 else "go"),
    # logistics v2: patrol, inventory and charging roles (interfaces §19.1)
    "patrol-next": lambda z: "skip" if z["access"] == "blocked" else ("enter-slow" if z["congestion"] >= 3 else "enter"),
    "join-alert": lambda a: "join" if a["severity"] == "high" else "ignore",
    "handle-discrepancy": lambda r: {"missing": "recheck", "mismatch": "relocate"}.get(r["status"], "none"),
    "reroute": lambda a: "detour" if a["kind"] == "obstacle" else "keep",
    # service scenarios (interfaces §19.1c): parking S-P, hotel S-H, hospital S-M
    "accept-car": lambda v: "lift-large" if v["size"] == "large" else "lift-small",
    "board-elevator": lambda e: "board" if e["door"] == "open" else "wait",
    "pick-car": lambda v, _loc: "to-exit" if v["exit"] == "requested" else "to-slot",
    "call-elevator": lambda c: "serve-" + c["robot"],
    "release-car": lambda loc: "release" if loc["spot"].startswith("gate-out") else "wait",
    "fetch-bag": lambda l: "cart" if l["weight"] >= 20 else "carry",
    "take-handover": lambda h: "take" if h is not None else "wait",
    "deliver-room": lambda r: "hold" if r["privacy"] == "dnd" else ("knock" if r["occupancy"] == "occupied" else "leave-at-door"),
    "prepare-handover": lambda loc: "grip" if loc["place"].startswith("handover") else "idle",
    "assign-room": lambda r: "deliver" if r["occupancy"] == "occupied" else "store",
    "pick-item": lambda m: "rush" if m["priority"] == "urgent" else "normal-run",
    "use-conveyor": lambda c: "load" if c["state"] == "running" else "carry-by-hand",
    "route-item": lambda loc: "transfer" if loc["place"] == "conveyor-in" else "idle",
    "receive-item": lambda loc: "receive" if loc["place"].startswith("ward") else "wait",
    "balance-load": lambda c: "divert" if c["load"] > 90 else "monitor",
    # patrol–charging domain (interfaces §19.4)
    "recall": lambda b: "return" if b["level"] < 20 else "continue",
    "redeploy": lambda i: {"high": "send-two", "low": "send-one"}.get(i["level"], "stand-down"),
    "assign-charger": lambda s: "assign" if s["free"] >= 1 else "queue",
    "patrol-step": lambda o: "goto-" + o["sector"],
    "patrol-step-ground": lambda o: "goto-" + o["sector"],
    "investigate": lambda i: {"high": "approach", "low": "observe"}.get(i["level"], "ignore"),
    "investigate-air": lambda i: {"high": "hover", "low": "flyby"}.get(i["level"], "ignore"),
    "dock": lambda r: "prepare-" + r["station"],
    "charge-check": lambda b: "release" if b["level"] >= 95 else "keep-charging",
}


# Tasks whose decision also uses the requester's own sensing, carried in the task request's
# params (the same request for every arm): check-bay gets the node the checker actually saw
# the cargo at (None = not found), go-charge the robot's own battery.
PARAM_DECISIONS = {
    "check-bay": lambda stored, p: ("missing" if p.get("observed") is None
                                    else "match" if stored["node"] == p["observed"] else "mismatch"),
    "go-charge": lambda ch, p: ("wait" if ch["occupancy"] == "occupied" else "go" if p["battery"] < 30 else "skip"),
}


def decide(kind, values, params=None):
    """Decision of task `kind` on its input values (dicts, task input order) and, for the kinds
    in PARAM_DECISIONS, the task params; None if the kind has no decision function or a value
    lacks a field the function needs."""
    try:
        if kind in PARAM_DECISIONS:
            return PARAM_DECISIONS[kind](*values, params or {})
        fn = DECISIONS.get(kind)
        return None if fn is None else fn(*values)
    except (KeyError, TypeError, ValueError):
        return None


@dataclass
class _Pending:
    task: Task
    t_received: float


@dataclass
class DecisionApp(ContextApp):
    """Local view + decision rule shared by all arms.

    view[(context, instance)] = (value, event_id). A task is decided as soon as the agent is
    not paused and every input is in the view; the decision record carries `result`, the
    task kind's decision function on the view values (DECISIONS). At its deadline an undecided
    task becomes `held` if the agent was paused at any time in [request, deadline], else `timeout`.
    """
    agent: str
    log: EventLog
    view: dict = field(default_factory=dict)
    paused: bool = False
    pending: list = field(default_factory=list)
    _pauses: list = field(default_factory=list)   # [t_start, t_end | None]
    observer: object = None                        # harness-only X1o watch (rcs.signal)

    def _observe(self, kind, context, instance, value):
        if self.observer is not None:
            self.observer.observe(kind, context, value, self.view.get((context, instance), (None,))[0])

    # arm-facing callbacks ------------------------------------------------------
    def on_deliver(self, context, instance, value, event_id):
        self._observe("deliver", context, instance, value)
        self.log.write("deliver", agent=self.agent, context=context, instance=instance,
                       event_id=event_id, value=value)
        if value is None:
            self.view.pop((context, instance), None)
        else:
            self.view[(context, instance)] = (value, event_id)
        self._try_pending()

    def on_current_value(self, context, instance, value, event_id):
        self._observe("current_value", context, instance, value)
        self.log.write("current_value", agent=self.agent, context=context, instance=instance,
                       event_id=event_id, value=value)
        self.view[(context, instance)] = (value, event_id)
        self._try_pending()

    def on_self_write(self, context, instance, value, event_id):
        """Harness-only: the agent's own write enters its view (logged as `emit`, not here)."""
        if value is None:
            self.view.pop((context, instance), None)
        else:
            self.view[(context, instance)] = (value, event_id)
        self._try_pending()

    def on_revoke(self, context, instance, notice_id):
        self._observe("revoke", context, instance, None)
        self.log.write("revoke", agent=self.agent, context=context, instance=instance, notice_id=notice_id)
        self.view.pop((context, instance), None)

    def set_paused(self, paused, reason=""):
        if paused == self.paused:
            return
        self.paused = paused
        known = self.log.clock.known
        now = self.log.clock.now() if known else float("-inf")   # paused during the warm-up
        if paused:
            self._pauses.append([now, None])
            self.log.write("pause", t=now if known else None, agent=self.agent, reason=reason)
        else:
            self._pauses[-1][1] = now
            self.log.write("resume", t=now if known else None, agent=self.agent, reason=reason)
            if known:
                self._try_pending()

    # harness-facing ------------------------------------------------------------
    def request(self, task: Task):
        now = self.log.clock.now()
        self.log.write("task", t=now, agent=self.agent, task_id=task.task_id, task_kind=task.kind,
                       inputs=task.inputs, deadline=task.deadline)
        self.pending.append(_Pending(task, now))
        self._try_pending()

    def tick(self, now):
        for p in [p for p in self.pending if now >= p.task.deadline]:
            self.pending.remove(p)
            outcome = "held" if self._paused_between(p.task.t, p.task.deadline) else "timeout"
            missing = [i for i in p.task.inputs if tuple(i) not in self.view]
            self.log.write("decision", t=now, agent=self.agent, task_id=p.task.task_id, outcome=outcome,
                           inputs=[], missing=missing, result=None, t_request=p.task.t, deadline=p.task.deadline)

    # decision rule ---------------------------------------------------------------
    def _try_pending(self):
        if self.paused or not self.pending:
            return
        now = self.log.clock.now()
        for p in list(self.pending):
            if now >= p.task.deadline:
                continue   # tick() records it as held/timeout
            keys = [tuple(i) for i in p.task.inputs]
            if p.task.kind == "take-handover" or all(k in self.view for k in keys):
                self.pending.remove(p)
                self.log.write("decision", t=now, agent=self.agent, task_id=p.task.task_id, outcome="decided",
                               inputs=[[c, i, self.view.get((c, i), (None, None))[1]] for c, i in keys], missing=[],
                               result=decide(p.task.kind, [self.view.get(k, (None, None))[0] for k in keys], p.task.params),
                               t_request=p.task.t, deadline=p.task.deadline)

    def _paused_between(self, a, b):
        return any(s <= b and (e is None or e >= a) for s, e in self._pauses)
