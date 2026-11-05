"""Common producer envelope (docs/interfaces.md §6.5): the one payload every arm sends for a
producer write, as JSON on std_msgs/String.

  {"schema": "rcs-env/1", "event_id": "e000123", "producer": "carrier1",
   "pv": {"n": 7, "ts": 812345678901}, "context": "RobotLocatedAt", "instance": "carrier1",
   "op": "upsert", "value": {...}}

`pv` is the producer instance version, the only ordering information a receiver may use:
  n   per (producer, context, instance) write counter of that producer, from 1
  ts  the producer's CLOCK_MONOTONIC reading at emission (ns). All processes run on one host
      and share this clock, which stands in for synchronised clocks in a real deployment.
The event ID is carried for logging and measurement only; it encodes the global trace order,
which a deployment would not have, so arms must not order by it.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

from rcs.trace import Event

SCHEMA = "rcs-env/1"


@dataclass
class Emitted(Event):
    """An Event as handed to the arm's emit(): the trace fields plus the producer version."""
    pv: dict | None = None


class Versioner:
    """Producer side: stamps each own write with its instance version."""

    def __init__(self, clock_ns=time.monotonic_ns):
        self._n = {}
        self._clock = clock_ns

    def stamp(self, e: Event) -> Emitted:
        x = (e.context, e.instance)
        self._n[x] = self._n.get(x, 0) + 1
        return Emitted(e.k, e.event_id, e.t, e.producer, e.context, e.instance, e.op, e.value,
                       pv={"n": self._n[x], "ts": self._clock()})


def envelope(e: Emitted) -> dict:
    return {"schema": SCHEMA, "event_id": e.event_id, "producer": e.producer, "pv": e.pv,
            "context": e.context, "instance": e.instance, "op": e.op, "value": e.value}


def dumps(env: dict) -> str:
    return json.dumps(env, separators=(",", ":"), ensure_ascii=False)


def loads(data: str) -> dict:
    env = json.loads(data)
    if env.get("schema") != SCHEMA:
        raise ValueError(f"not an {SCHEMA} envelope")
    return env


def order_key(env: dict):
    """Total order of writes to one (context, instance): producer clock, then producer id,
    then the producer's own counter. A receiver keeps the write with the largest key and
    drops any envelope whose key is not larger than the last one it applied (stale or duplicate)."""
    return (env["pv"]["ts"], env["producer"], env["pv"]["n"])


def newer(env: dict, last_key) -> bool:
    return last_key is None or order_key(env) > tuple(last_key)
