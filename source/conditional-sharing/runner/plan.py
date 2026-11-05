"""Fixed decision code of the Manager plan (identical for every arm; its sha256 is recorded).

The plan does not evaluate thresholds itself: it registers a robot on the low-power exclusion
list while a RobotStatus fact of that robot is in the Manager's eligible view, and raises a
stop-anomaly suspicion flag while a RobotStopped fact is there. A robot without flags has no
evidence for either; that is NOT a judgement that it is safe, normal or reassignable, and no
task is reclaimed or reassigned here.
"""

FLAGS = ("low_power_excluded", "stop_suspect")


def decide(view, robots):
    """view: {(context, instance): value}; robots: fixed list from the decision schedule."""
    out = {}
    for r in robots:
        flags = []
        if ("RobotStatus", r) in view:
            flags.append("low_power_excluded")
        if ("RobotStopped", r) in view:
            flags.append("stop_suspect")
        out[r] = flags
    return out
