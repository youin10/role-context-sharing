"""Major 1 driver: runs configurations in increasing m, one child process each, under the
budget of budget.json (or overriding limits for the dry run).

Watchdog: the parent polls the child's RSS (`ps -o rss=`, KiB) every 0.1 s and kills the
child (SIGKILL) on peak_rss_bytes or per_config_wall_s overrun -> status=aborted row. A child
exit code 3 means a timed call exceeded per_call_s -> status=stopped. After aborted/stopped
no larger m of the same family is started. Every driver row is flushed immediately.

  python -B driver.py <run_dir> [--families OR,AND,DUP,REF] [--only NAME] [--rss BYTES]
                      [--wall S] [--call S] [--reps N]
"""
import argparse, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
B = json.load(open(os.path.join(HERE, "budget.json")))


def rss_bytes(pid):
    try:
        out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
        return int(out) * 1024 if out else 0
    except ValueError:
        return 0


def run_one(name, run_dir, a, log):
    raw = os.path.join(run_dir, f"{name}.jsonl")
    cmd = [PY, "-B", os.path.join(HERE, "run_config.py"), os.path.join(HERE, "inputs"), name, raw, str(a.reps), str(a.call)]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="0")
    t0 = time.time()
    with open(os.path.join(run_dir, f"{name}.stderr.txt"), "w") as err:
        p = subprocess.Popen(cmd, stdout=err, stderr=err, env=env)
        peak, status, reason = 0, None, None
        while p.poll() is None:
            r = rss_bytes(p.pid)
            peak = max(peak, r)
            el = time.time() - t0
            if r > a.rss:
                status, reason = "aborted", f"rss {r} > {a.rss}"
            elif el > a.wall:
                status, reason = "aborted", f"wall {el:.1f}s > {a.wall}s"
            if status:
                p.kill()
                p.wait()
                break
            time.sleep(0.1)
    el = time.time() - t0
    rc = p.returncode
    if status is None:
        status = {0: "ok", 3: "stopped", 4: "check_failed"}.get(rc, "error")
    row = {"config": name, "status": status, "reason": reason, "rc": rc, "elapsed_s": round(el, 3),
           "peak_rss_polled_bytes": peak, "cmd": cmd, "limits": {"rss": a.rss, "wall": a.wall, "call": a.call, "reps": a.reps},
           "t_start": t0}
    log.write(json.dumps(row) + "\n")
    log.flush()
    print(json.dumps({k: row[k] for k in ("config", "status", "reason", "rc", "elapsed_s", "peak_rss_polled_bytes")}), flush=True)
    return status


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--families", default="REF,OR,AND,DUP")
    ap.add_argument("--only")
    ap.add_argument("--rss", type=int, default=B["stop_rules"]["peak_rss_bytes"])
    ap.add_argument("--wall", type=float, default=B["stop_rules"]["per_config_wall_s"])
    ap.add_argument("--call", type=float, default=B["stop_rules"]["per_call_s"])
    ap.add_argument("--total", type=float, default=B["stop_rules"]["total_wall_s"])
    ap.add_argument("--reps", type=int, default=B["repetitions"]["measured"])
    a = ap.parse_args()
    os.makedirs(a.run_dir, exist_ok=True)
    log = open(os.path.join(a.run_dir, "driver.jsonl"), "a")
    seq = B["m_sequence"]
    plan = {"REF": [0], "OR": seq["required"] + seq["extension"], "AND": seq["required"] + seq["extension"], "DUP": seq["DUP"]}
    t0 = time.time()
    names = [a.only] if a.only else [f"{f}-m{m:02d}" for f in a.families.split(",") for m in plan[f]]
    stopped_family = set()
    for name in names:
        fam = name.split("-")[0]
        if fam in stopped_family:
            log.write(json.dumps({"config": name, "status": "not_started", "reason": f"{fam} stopped at a smaller m"}) + "\n")
            log.flush()
            continue
        if time.time() - t0 > a.total:
            log.write(json.dumps({"config": name, "status": "not_started", "reason": "total_wall_s exceeded"}) + "\n")
            log.flush()
            continue
        st = run_one(name, a.run_dir, a, log)
        if st in ("aborted", "stopped", "error"):
            stopped_family.add(fam)
    log.close()


if __name__ == "__main__":
    main()
