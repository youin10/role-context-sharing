"""Ground-truth configuration timeline used only by trace generation (never by an arm)."""
from __future__ import annotations

import bisect
from dataclasses import dataclass

from rcs.model import Cfg


@dataclass
class CfgTimeline:
    points: list[tuple[float, Cfg]]  # (t_from, cfg), sorted, first at 0.0

    def at(self, t) -> Cfg:
        i = bisect.bisect_right([p[0] for p in self.points], t) - 1
        return self.points[max(i, 0)][1]

    def roles_of(self, agent, t):
        return self.at(t).assignment.agents.get(agent, [])

    def may_change(self, agent, context, t):
        cfg = self.at(t)
        return any(context in cfg.needs.role(r).changes for r in cfg.assignment.agents.get(agent, []))

    def all_agents(self):
        seen = []
        for _, cfg in self.points:
            for a in cfg.assignment.agents:
                if a not in seen:
                    seen.append(a)
        return seen
