"""Validation behaviour of the frozen core on this experiment's inputs. No simulator."""
import json
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from wcs.core import api, core_run  # noqa: E402
from wcs.sharing import envelope  # noqa: E402
from arms.a.typed import check_plans, check_rule  # noqa: E402
from arms.d.generator import GenerationError, generate  # noqa: E402
from arms.d.spec import OrgError, load_binding, load_spec_org  # noqa: E402

CONFIG = os.path.join(ROOT, "config")


def path(rel):
    return os.path.join(CONFIG, rel)


def gen_case(case, cat, types):
    try:
        gen = generate(load_spec_org(path(case["model"]), cat), load_binding(path(case["binding"])), types)
    except GenerationError as e:
        return {"outcome": "refuse", "codes": sorted({f.code for f in e.findings})}, None
    except OrgError as e:
        return {"outcome": "refuse", "codes": [e.code]}, None
    return {"outcome": "accept", "codes": []}, gen


def scenario():
    return {"id": "static", "d": {"model": path("d/transit-r0"), "binding": path("d/b-transit")},
            "a": {"initial": "initial-r0"}, "observe": ["manager1"], "steps": []}


def run_arm(arm):
    r = core_run.DRun(scenario(), {}) if arm == "D" else core_run.ARun(scenario(), {})
    if arm == "A":
        r.arm_dir = path("a-hand")
    r.start()
    return r


def main():
    with open(path("static/expected.yml")) as f:
        exp = yaml.safe_load(f)
    cat, types = api.catalogue()
    results, fails = [], []

    def record(case_id, ok, observed):
        results.append({"id": case_id, "ok": bool(ok), "observed": observed})
        if not ok:
            fails.append(case_id)

    for case in exp["d_generation"]:
        obs, gen = gen_case(case, cat, types)
        ok = obs["outcome"] == case["expect"] and (case["expect"] == "accept" or obs["codes"] == [case["code"]])
        if gen and "consumers" in case:
            got = {a: sorted(v) for a, v in gen["consumers"].items() if v}
            ok = ok and got == case["consumers"] and gen["producers"] == case.get("producers", gen["producers"])
            obs["consumers"], obs["producers"] = got, gen["producers"]
        if gen and "alternatives" in case:
            n = len(gen["consumers"]["manager1"]["RobotLocatedAt"])
            ok = ok and n == case["alternatives"]
            obs["alternatives"] = n
        record(case["id"], ok, obs)

    signature = api.signature()
    for rel in exp["a_rules"]["valid_plan_dirs"]:
        found = check_plans(path(rel), signature, types)
        record(f"A-valid:{rel}", not found, found)
    with open(path(exp["a_rules"]["bad_rules"])) as f:
        bad = yaml.safe_load(f)
    for n, item in enumerate(bad, 1):
        codes = [c for c, _ in check_rule(item["rule"], signature, types)]
        record(f"A-bad-{n}", item["code"] in codes, codes)

    for case in exp["reports"]:
        for arm in ("D", "A"):
            r = run_arm(arm)
            env = envelope("static", "wheel1", "RobotLocatedAt", case["instance"], 1, 1, case["value"])
            _, rejected = r.report(env)
            codes = [x["code"] for x in rejected]
            record(f"{case['id']}-{arm}", case["code"] in codes and not r.store(), {"codes": codes, "store": r.store()})

    o = exp["outside_report_configuration"]
    r = run_arm("D")
    env = envelope("static", o["producer"], "RobotLocatedAt", o["instance"], 1, 1, o["value"])
    r.report(env)
    n = r.sm.stats["outside_report_cfg"]
    record("O1-D", n == o["d_outside_report_cfg"], {"outside_report_cfg": n, "store": r.store()})

    print(json.dumps({"pass": not fails, "fails": fails, "cases": results}, ensure_ascii=False, indent=1))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
