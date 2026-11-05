"""DDS minimum ping smoke (preparation only, not a paper result).

Two processes in two containers on one bridge network: `pong` echoes /cs_smoke/ping onto
/cs_smoke/pong; `ping` waits for matching, sends N pings and records round-trip times.
Writes one JSON line per message to $OUT/<role>.jsonl and a summary on stdout.

  python3 ping.py pong|ping [N]
"""
import json
import os
import sys
import time

import rclpy
import rclpy.utilities
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

QOS = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=100, reliability=ReliabilityPolicy.RELIABLE,
                 durability=DurabilityPolicy.VOLATILE)


def main():
    role, n = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 20
    out = open(os.path.join(os.environ.get("OUT", "/tmp"), f"{role}.jsonl"), "w")

    def log(**kw):
        out.write(json.dumps({"t_ns": time.monotonic_ns(), "role": role, **kw}) + "\n")
        out.flush()

    rclpy.init()
    node = rclpy.create_node(f"cs_smoke_{role}")
    log(kind="env", rmw=rclpy.utilities.get_rmw_implementation_identifier(),
        domain=os.environ.get("ROS_DOMAIN_ID"), host=os.uname().nodename, pid=os.getpid())
    if role == "pong":
        pub = node.create_publisher(String, "/cs_smoke/pong", QOS)
        seen = []

        def on(m):
            log(kind="rx", data=m.data)
            pub.publish(String(data=m.data))
            seen.append(1)
        node.create_subscription(String, "/cs_smoke/ping", on, QOS)
        end = time.monotonic() + 60
        while len(seen) < n and time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=0.05)
        t = time.monotonic() + 1.0          # let the last pong drain
        while time.monotonic() < t:
            rclpy.spin_once(node, timeout_sec=0.05)
        print(json.dumps({"role": role, "echoed": len(seen)}))
    else:
        pub = node.create_publisher(String, "/cs_smoke/ping", QOS)
        rtt, got = [], {}
        node.create_subscription(String, "/cs_smoke/pong", lambda m: got.setdefault(m.data, time.monotonic_ns()), QOS)
        end = time.monotonic() + 30
        while (pub.get_subscription_count() < 1 or node.count_publishers("/cs_smoke/pong") < 1) \
                and time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=0.05)
        log(kind="matched", subs=pub.get_subscription_count())
        for k in range(n):
            data = f"p{k}"
            t0 = time.monotonic_ns()
            pub.publish(String(data=data))
            log(kind="tx", data=data)
            while data not in got and time.monotonic_ns() - t0 < 2e9:
                rclpy.spin_once(node, timeout_sec=0.01)
            if data in got:
                rtt.append((got[data] - t0) / 1e6)
                log(kind="rx", data=data, rtt_ms=rtt[-1])
        rtt.sort()
        print(json.dumps({"role": role, "sent": n, "received": len(rtt),
                          "rtt_ms_median": rtt[len(rtt) // 2] if rtt else None,
                          "rtt_ms_max": rtt[-1] if rtt else None}))
    node.destroy_node()
    rclpy.shutdown()
    out.close()


if __name__ == "__main__":
    main()
