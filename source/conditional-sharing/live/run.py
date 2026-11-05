#!/usr/bin/env python3
"""Host runner for one live run (stdlib only): one container per process on a fresh labelled
bridge network with a unique ROS_DOMAIN_ID, sequential, then the independent judge.

  python3 live/run.py --arm d|a --scenario contract/CT1 --expected contract/CT1 [--rep 1]
                      [--label prep] [--out-root live/runs/<dir>] [--a-variant helper]
                      [--expect-snapshot <core snapshot sha256>]

Output: <out-root>/<run_id>/ {plan.json, manifest.json, logs/<proc>.jsonl, logs/<proc>.stdout,
judge.json, nc.json}. Core snapshot = sha256 over sorted "relpath\0sha256\n" lines of every
file of the core snapshot members (tools/snapshot.py); --expect-snapshot (digest or ID
cs-core-<12>) refuses to run on any other snapshot. Only containers and the network labelled cslive.run=<run_id> are created and
removed; nothing else on the host is touched. Fails (exit != 0) on any container error or a
judge FAIL; failed runs are kept, never deleted.
"""
import argparse
import hashlib
import json
import os
import random
import shlex
import subprocess
import sys
import time

LIVE = os.path.dirname(os.path.abspath(__file__))
CS = os.path.dirname(LIVE)
REPO = os.path.dirname(os.path.dirname(CS))
IMAGE = "rcs-experiments:jazzy"
BASE = "ros:jazzy@sha256:103b6c417973394659af6804d4917cd489b91e5ed22eb7bef263025a3bed2410"
WAIT_S = 300


def sh(cmd, check=True, capture=True):
    r = subprocess.run(cmd, capture_output=capture, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{shlex.join(cmd)} -> {r.returncode}\n{r.stderr}")
    return r.stdout.strip() if capture else ""


def tree_hashes(root, subdirs):
    out = {}
    for sd in subdirs:
        for dp, dns, fns in os.walk(os.path.join(root, sd)):
            dns[:] = sorted(d for d in dns if d not in ("__pycache__", "runs", ".venv"))
            for fn in sorted(fns):
                p = os.path.join(dp, fn)
                with open(p, "rb") as f:
                    out[os.path.relpath(p, root)] = hashlib.sha256(f.read()).hexdigest()
    agg = hashlib.sha256("".join(f"{k}\0{v}\n" for k, v in sorted(out.items())).encode()).hexdigest()
    return out, agg


def used_domains():
    ids = sh(["docker", "ps", "-q", "--filter", "label=cslive=1"]).split()
    doms = set()
    for c in ids:
        for e in json.loads(sh(["docker", "inspect", "-f", "{{json .Config.Env}}", c])):
            if e.startswith("ROS_DOMAIN_ID="):
                doms.add(int(e.split("=")[1]))
    return doms


def core_snapshot():
    """The core worker's tree digest (tools/snapshot.py: tree() + digest()), computed by its own
    stdlib code so both sides name the same snapshot (ID cs-core-<digest[:12]>)."""
    sys.path.insert(0, os.path.join(CS, "tools"))
    import snapshot
    files = snapshot.tree(CS)
    return files, snapshot.digest(files)


def live_snapshot():
    h, _ = tree_hashes(LIVE, ["cslive", "smoke"])
    for fn in ("judge.py", "nc_raw.py", "run.py", "README.md"):
        with open(os.path.join(LIVE, fn), "rb") as f:
            h[fn] = hashlib.sha256(f.read()).hexdigest()
    return h, hashlib.sha256("".join(f"{k}\0{v}\n" for k, v in sorted(h.items())).encode()).hexdigest()


def docker_base(rid, net, dom, run_dir, extra_env):
    env = {"ROS_DOMAIN_ID": str(dom), "CS_RUN": "/run", "CS_ROOT": "/cs", "PYTHONPATH": "/cs/runner:/cs/src:/cs/live",
           "PYTHONDONTWRITEBYTECODE": "1", **extra_env}
    cmd = ["docker", "run", "--label", "cslive=1", "--label", f"cslive.run={rid}", "-v", f"{CS}:/cs:ro",
           "-v", f"{run_dir}:/run"]
    if net:
        cmd += ["--network", net]
    for k, v in env.items():
        cmd += ["-e", f"{k}={v}"]
    return cmd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["d", "a"], required=True)
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--expected", required=True)
    ap.add_argument("--rep", type=int, default=1)
    ap.add_argument("--label", default="prep")
    ap.add_argument("--out-root", default=os.path.join(LIVE, "runs"))
    ap.add_argument("--a-variant")
    ap.add_argument("--no-guard", action="store_true")
    ap.add_argument("--expect-snapshot")
    a = ap.parse_args()
    core_files, core_agg = core_snapshot()
    if a.expect_snapshot and a.expect_snapshot not in (core_agg, "cs-core-" + core_agg[:12]):
        sys.exit(f"core snapshot {core_agg} != expected {a.expect_snapshot}; refusing to run")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    rid = f"{a.label}-{a.arm}-{a.scenario.replace('/', '_')}-r{a.rep}-{stamp}"
    run_dir = os.path.join(os.path.abspath(a.out_root), rid)
    os.makedirs(os.path.join(run_dir, "logs"))
    taken = used_domains()
    dom = random.choice([d for d in range(100, 200) if d not in taken])
    net = f"cslive-{rid}"
    extra = {"CS_A_GUARD": "0" if a.no_guard else "1"}
    sc_in = f"/cs/inputs/scenarios/{a.scenario}.yml"
    commands = [shlex.join(sys.argv)]

    # 1 plan (no network)
    cmd = docker_base(rid, None, dom, run_dir, extra) + ["--rm", "--network", "none", IMAGE, "bash", "-c",
           f"source /opt/ros/jazzy/setup.bash && python3 -m cslive.plan {sc_in} {a.arm} /run/plan.json {a.a_variant or '-'}"]
    commands.append(shlex.join(cmd))
    sh(cmd)
    with open(os.path.join(run_dir, "plan.json")) as f:
        plan = json.load(f)

    # 2 manifest before the run
    live_h, live_agg = live_snapshot()
    probe = docker_base(rid, None, dom, run_dir, extra) + ["--rm", "--network", "none", IMAGE, "bash", "-c",
             "source /opt/ros/jazzy/setup.bash && python3 -c 'import sys,yaml;print(sys.version.split()[0],yaml.__version__)' "
             "&& dpkg-query -W ros-jazzy-rclpy ros-jazzy-rmw-fastrtps-cpp ros-jazzy-fastrtps && echo RMW=$RMW_IMPLEMENTATION"]
    manifest = {
        "schema": "cslive-manifest/1", "run_id": rid, "arm": a.arm, "scenario": a.scenario, "rep": a.rep,
        "label": a.label, "started": stamp, "ros_domain_id": dom, "network": net,
        "image": IMAGE, "image_id": sh(["docker", "image", "inspect", "-f", "{{.Id}}", IMAGE]),
        "image_base": BASE, "image_env_probe": sh(probe).splitlines(),
        "docker": sh(["docker", "version", "--format", "{{.Server.Version}} {{.Server.Os}}/{{.Server.Arch}}"]),
        "repo_head": sh(["git", "-C", REPO, "rev-parse", "HEAD"]),
        "core_snapshot_sha256": core_agg, "core_snapshot_id": "cs-core-" + core_agg[:12], "live_sha256": live_agg,
        "scenario_sha256": hashlib.sha256(open(os.path.join(CS, "inputs", "scenarios", a.scenario + ".yml"), "rb").read()).hexdigest(),
        "expected_sha256": hashlib.sha256(open(os.path.join(CS, "inputs", "expected", a.expected + ".yml"), "rb").read()).hexdigest(),
        "plan_sha256": hashlib.sha256(open(os.path.join(CS, "runner", "plan.py"), "rb").read()).hexdigest(),
        "files": {"core": core_files, "live": live_h},
        "a_variant": a.a_variant, "a_guard": not a.no_guard, "plan": plan, "commands": commands,
    }

    # 3 processes, one container each; driver last
    t_start = time.monotonic()
    procs = [p for p in plan["procs"] if p != "driver"] + ["driver"]
    names = {p: f"cslive-{rid}-{p}" for p in procs}
    status = {}
    try:
        sh(["docker", "network", "create", "--label", "cslive=1", "--label", f"cslive.run={rid}", net])
        for p in procs:
            cmd = docker_base(rid, net, dom, run_dir, extra | {"CS_PROC": p}) + [
                "-d", "--name", names[p], "--hostname", p, IMAGE, "bash", "-c",
                "source /opt/ros/jazzy/setup.bash && exec python3 -m cslive.proc"]
            commands.append(shlex.join(cmd))
            sh(cmd)
        end = time.monotonic() + WAIT_S
        for p in ["driver"] + procs[:-1]:
            left = max(1, int(end - time.monotonic()))
            r = subprocess.run(["docker", "wait", names[p]], capture_output=True, text=True, timeout=left)
            status[p] = int(r.stdout.strip() or -1)
    except subprocess.TimeoutExpired:
        status["timeout"] = True
    finally:
        for p in procs:
            with open(os.path.join(run_dir, "logs", f"{p}.stdout"), "w") as f:
                subprocess.run(["docker", "logs", names[p]], stdout=f, stderr=subprocess.STDOUT)
        sh(["docker", "rm", "-f"] + list(names.values()), check=False)
        sh(["docker", "network", "rm", net], check=False)
        manifest["exit_codes"] = status
        manifest["wall_s"] = round(time.monotonic() - t_start, 2)
        manifest["finished"] = time.strftime("%Y%m%d-%H%M%S")
        with open(os.path.join(run_dir, "manifest.json"), "w") as f:
            json.dump(manifest, f, indent=1)

    # 4 independent judge + raw negative controls (isolated interpreter, no src/runner on the path)
    rc = 0
    manifest["judge"] = {}
    for tool, out in (("judge.py", "judge.json"), ("nc_raw.py", "nc.json")):
        cmd = ["docker", "run", "--rm", "--network", "none", "--label", "cslive=1", "--label", f"cslive.run={rid}",
               "-v", f"{LIVE}/judge.py:/j/judge.py:ro", "-v", f"{LIVE}/nc_raw.py:/j/nc_raw.py:ro",
               "-v", f"{CS}/inputs:/inputs:ro", "-v", f"{run_dir}:/run", IMAGE,
               "python3", "-I", f"/j/{tool}", "/run", a.arm, f"/inputs/scenarios/{a.scenario}.yml",
               f"/inputs/expected/{a.expected}.yml", f"/run/{out}"]
        manifest["commands"].append(shlex.join(cmd))
        r = subprocess.run(cmd, capture_output=True, text=True)
        print(tool, r.stdout.strip()[-1500:], r.stderr.strip()[-1500:])
        manifest["judge"][tool] = r.returncode
        rc = rc or r.returncode
    with open(os.path.join(run_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    bad = {p: c for p, c in status.items() if c != 0}
    print(json.dumps({"run_id": rid, "domain": dom, "exit_codes": status}))
    sys.exit(1 if bad or rc else 0)


if __name__ == "__main__":
    main()
