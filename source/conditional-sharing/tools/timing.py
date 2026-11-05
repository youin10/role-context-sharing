"""Core-level timing (in-process, no ROS). cold = a fresh interpreter that loads the inputs and
builds the configuration / loads the plans once; warm = repeated operations in one process.
These numbers describe this core harness only; they are not a performance comparison claim.

  python tools/timing.py <out.json>
"""
import json, os, statistics, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "runner"))

COLD = {
    "D_generate_M1": "import core_run as c; r=c.DRun({'d':{'model':'M1','binding':'b-main'},'id':'cold'},{}); r.start()",
    "A_load_initial_v1": "import core_run as c; r=c.ARun({'a':{'initial':'initial-main-v1'},'id':'cold'},{}); r.start()",
}


def cold(n=7):
    out = {}
    for name, code in COLD.items():
        ts = []
        for _ in range(n):
            t = time.perf_counter()
            subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {os.path.join(ROOT, 'runner')!r}); {code}"],
                           check=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            ts.append(time.perf_counter() - t)
        out[name] = {"n": n, "median_s": statistics.median(ts), "min_s": min(ts), "max_s": max(ts),
                     "includes": "interpreter start, imports, ontology/type loading, parse+check+generate or plan load"}
    return out


def warm(n=2000):
    import core_run as c
    out = {}
    d = c.DRun({"d": {"model": "M1", "binding": "b-main"}, "id": "warm"}, {})
    d.start()
    t = time.perf_counter()
    for k in range(200):
        d.gen("M1", "b-main")
    out["D_generate_M1"] = {"n": 200, "mean_ms": (time.perf_counter() - t) / 200 * 1e3}
    t = time.perf_counter()
    for k in range(n):
        d.report({"schema": "rcs-env/1", "event_id": f"w{k}", "producer": "biped1", "pv": {"n": k + 1, "ts": k + 1},
                  "context": "RobotStatus", "instance": "biped1", "op": "upsert",
                  "value": {"battery": 25 + (k % 10), "zone": "storage"}})
    out["D_report_route_notify"] = {"n": n, "mean_us": (time.perf_counter() - t) / n * 1e6}
    a = c.ARun({"a": {"initial": "initial-main-v1"}, "id": "warm"}, {})
    a.start()
    t = time.perf_counter()
    for k in range(n):
        a.report({"schema": "rcs-env/1", "event_id": f"w{k}", "producer": "biped1", "pv": {"n": k + 1, "ts": k + 1},
                  "context": "RobotStatus", "instance": "biped1", "op": "upsert",
                  "value": {"battery": 25 + (k % 10), "zone": "storage"}})
    out["A_report_bus_ltm_agent"] = {"n": n, "mean_us": (time.perf_counter() - t) / n * 1e6}
    return out


if __name__ == "__main__":
    res = {"cold": cold(), "warm": warm(), "python": sys.version,
           "note": "core harness only; D report = SM routing + AgentCore; A report = in-process bus + LTM + agents. Not a ROS/distributed measurement and not a superiority claim."}
    json.dump(res, open(sys.argv[1], "w"), indent=1)
    print(json.dumps(res, indent=1))
