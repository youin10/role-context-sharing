"""Runs one scenario in a fresh Compose project and removes that project afterwards.

  run_one.py --scenario TR1 --arm D --rep 1 --label dev [--fault NAME]
"""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from wcs.core import CORE  # noqa: E402
from wcs.driver import Driver  # noqa: E402
from wcs.io import Link  # noqa: E402
from wcs.sharing import Arm  # noqa: E402
from wcs.topology import Topology  # noqa: E402

MQTT_PORT = os.environ.get("WCS_MQTT_PORT", "18883")
FAULTS = ["drop-retract", "stale-config", "boundary", "no-validation", "per-role-retract", "dup-branch",
          "non-transitive"]
IMAGE = os.environ.get("WCS_IMAGE", "wcs-webots:R2025a")
IMAGES = [IMAGE, "eclipse-mosquitto:2"]


def sh(args, env=None, check=True):
    return subprocess.run(args, env=env, check=check, capture_output=True, text=True)


def tree_hash(top):
    h = hashlib.sha256()
    for base, dirs, files in sorted(os.walk(top)):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for name in sorted(files):
            if name.endswith(".pyc"):
                continue
            p = os.path.join(base, name)
            h.update(os.path.relpath(p, top).encode())
            with open(p, "rb") as f:
                h.update(f.read())
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--arm", required=True, choices=["D", "A", "H"])
    ap.add_argument("--rep", required=True, type=int)
    ap.add_argument("--label", required=True)
    ap.add_argument("--fault", choices=FAULTS)
    a = ap.parse_args()

    name = f"{a.scenario}-{a.arm}-{a.rep}" + (f"-{a.fault}" if a.fault else "")
    out = os.path.join(ROOT, "records", a.label, name)
    if os.path.exists(out):
        sys.exit(f"refusing to overwrite {out}")
    os.makedirs(os.path.join(out, "shots"))

    with open(os.path.join(ROOT, "config", "scenarios", a.scenario + ".yml")) as f:
        scenario = yaml.safe_load(f)
    project = "wcs-" + f"{a.label}-{name}".lower()
    compose = ["docker", "compose", "-f", os.path.join(ROOT, "sim", "compose.yml")]
    env = {**os.environ, "WCS_PROJECT": project, "WCS_MQTT_PORT": MQTT_PORT, "WCS_OUT": os.path.join(out, "shots")}
    manifest = {
        "run": name, "label": a.label, "scenario": a.scenario, "arm": a.arm, "rep": a.rep, "fault": a.fault,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "compose_project": project, "python": platform.python_version(),
        "core_tree_sha256": tree_hash(CORE),
        "config_sha256": tree_hash(os.path.join(ROOT, "config")), "sim_sha256": tree_hash(os.path.join(ROOT, "sim")),
        "wcs_sha256": tree_hash(os.path.join(ROOT, "wcs")),
        "images": {i: sh(["docker", "image", "inspect", i, "--format", "{{.Id}}"]).stdout.strip() for i in IMAGES},
    }
    status = "not-run"
    try:
        sh(compose + ["up", "-d"], env=env)
        link = Link(int(MQTT_PORT), project)
        try:
            arm = Arm(a.arm, scenario, a.fault)
            topo = Topology(os.path.join(ROOT, "config", "topology.yml"))
            status = Driver(project, scenario, arm, topo, link, os.path.join(out, "events.jsonl")).run()
        finally:
            link.close()
    finally:
        with open(os.path.join(out, "containers.log"), "w") as f:
            f.write(subprocess.run(compose + ["logs", "--no-color", "--timestamps"], env=env, capture_output=True,
                                   text=True).stdout)
        sh(compose + ["down", "-v", "--remove-orphans"], env=env, check=False)
        manifest["status"] = status
        manifest["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with open(os.path.join(out, "manifest.json"), "w") as f:
            json.dump(manifest, f, indent=1, sort_keys=True)
    print(name, status)


if __name__ == "__main__":
    main()
