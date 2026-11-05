"""Live transport: topics, QoS and JSON payloads on std_msgs/String.

Topic names follow rcs-experiments arms/d/wire.py and arms/a/wire.py (7bef3ecd); the A topics
take a /cs prefix so they cannot be confused with the old runs. QoS differs on purpose: every
topic is RELIABLE + TRANSIENT_LOCAL with a deep KEEP_LAST history, so a reader that matches
late still gets every message in writer order. No fault is injected and no recovery path is
exercised (out of scope); QoS is transport configuration, not core semantics.
"""
import json

from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy

CTL = "/cs/ctl"            # driver -> all: arm / go / end
READY = "/cs/ready"        # all -> driver: hello and per-step ready

D_REPORT = "/d/report"     # producer -> SM
D_APPLY = "/d/apply"       # driver (applier) -> SM: generated configurations
D_ACK = "/d/ack"           # agent -> SM: commit acknowledgements

A_LTM = "/cs/a/ltm"        # agent / driver -> LTM


def d_inbox(agent):
    return f"/d/inbox/{agent}"


def a_inbox(agent):
    return f"/cs/a/to/{agent}"


QOS = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=10000, reliability=ReliabilityPolicy.RELIABLE,
                 durability=DurabilityPolicy.TRANSIENT_LOCAL)
QOS_DESC = {"history": "KEEP_LAST", "depth": 10000, "reliability": "RELIABLE", "durability": "TRANSIENT_LOCAL"}


def dumps(obj):
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False, sort_keys=True)


def data_topics(plan):
    ags = plan["agents"]
    if plan["arm"] == "d":
        return [D_REPORT, D_APPLY, D_ACK] + [d_inbox(a) for a in ags]
    return [A_LTM] + [a_inbox(a) for a in ags]
