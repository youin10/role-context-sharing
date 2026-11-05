"""Run the whole core experiment and write results/<run_id>/.

  python runner/run_all.py <run_id>            (from experiments/conditional-sharing)

Writes raw/<group>/<scenario>__<arm>__<variant>.jsonl (one record per step), judgments.json,
grammar.json, a_static.json, x1.json, summary.json, coverage.md and manifest.json. Exit status 1 if
a main run fails, a contrast/negative control unexpectedly passes, or an audit check fails.
Raw logs of failing runs are kept (negative controls fail on purpose).
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import platform
import subprocess
import sys
import time

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import core_run  # noqa: E402
import judge  # noqa: E402
import variants as V  # noqa: E402
from arms.a.typed import check_plans, check_rule  # noqa: E402
from arms.d.checker import check  # noqa: E402
from arms.d.generator import GenerationError, generate  # noqa: E402
from arms.d.ontology import signature_of  # noqa: E402
from arms.d.spec import Binding, OrgError, parse_org  # noqa: E402

INPUTS = os.path.join(ROOT, "inputs")
NS = core_run.NS


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def scenario_of(sid):
    with open(sc_path(sid)) as f:
        return yaml.safe_load(f)


def sc_path(sid):
    p = os.path.join(INPUTS, "scenarios", sid + ".yml")
    return p if os.path.exists(p) else os.path.join(INPUTS, "scenarios", "contract", sid + ".yml")


def exp_path(sid):
    p = os.path.join(INPUTS, "expected", sid + ".yml")
    return p if os.path.exists(p) else os.path.join(INPUTS, "expected", "contract", sid + ".yml")


MAIN = ["B1", "T", "B2", "B3", "K", "S1", "P1", "X2", "CT1", "CT2", "CT3", "CT4", "CT5", "CT6", "CT7-cfg1", "CT7-cfg0"]

# (scenario, arm, label, variant, requirement it breaks)
CONTRASTS = [
    ("P1", "D", "noupdate", {"skip_changes": True}, "fixed plan without the model update"),
    ("P1", "D", "nocond", {"model_map": {"M1": "M-nocond", "M2": "M-nocond"}}, "fixed plan without data conditions"),
    ("P1", "A", "noupdate", {"skip_changes": True}, "fixed plan without the plan update"),
    ("P1", "A", "nocond", {"initial_map": {"initial-main-v1": "initial-main-nocond"}, "skip_changes": True},
     "fixed plan with unconditional rules"),
]
NEGATIVE = [
    ("B1", "D", "boundary-lt", {"model_map": {"M1": "M1-strict"}}, "boundary error (< instead of <=)"),
    ("B1", "A", "boundary-lt", {"initial_map": {"initial-main-v1": "initial-main-strict"}}, "boundary error (< instead of <=)"),
    ("CT1", "D", "boundary-lt", {"model_map": {"contract/CT-typed": "nc/CT-typed-strict"}}, "boundary error (< instead of <=)"),
    ("B1", "D", "no-retract", {"sm_cls": V.NoRetractSM}, "retract omission on condition exit"),
    ("CT3", "D", "no-retract", {"sm_cls": V.NoRetractSM}, "retract omission on condition exit"),
    ("B1", "A", "asis", {"asis": True}, "retract omission (A-asis: no exit watch, no tombstones)"),
    ("CT3", "A", "asis", {"asis": True}, "retract omission (A-asis: no exit watch, no tombstones)"),
    ("B1", "D", "signature-as-type", {"sm_cls": V.SignatureOnlySM}, "wrong-type reception"),
    ("CT1", "D", "signature-as-type", {"sm_cls": V.SignatureOnlySM}, "wrong-type reception"),
    ("B1", "D", "non-transitive", {"sm_cls": V.NonTransitiveSM}, "subclass missing"),
    ("CT1", "D", "non-transitive", {"sm_cls": V.NonTransitiveSM}, "subclass missing"),
    ("B3", "D", "per-role-retract", {"sm_cls": V.PerRoleRetractSM}, "residual-support mistake"),
    ("CT5", "D", "per-role-retract", {"sm_cls": V.PerRoleRetractSM}, "residual-support mistake"),
    ("B2", "D", "stale-model", {"skip_changes": True}, "model not updated"),
    ("B2", "A", "stale-model", {"skip_changes": True}, "plan not updated"),
    ("CT4", "D", "stale-model", {"skip_changes": True}, "model not updated"),
    ("CT4", "A", "stale-model", {"skip_changes": True}, "plan not updated"),
    ("S1", "D", "stop-299", {"model_map": {"M1": "nc/M1-stop299"}}, "RobotStopped early entry at 299 s"),
    ("CT6", "D", "stop-299", {"model_map": {"contract/CT-typed": "nc/CT-typed-stop299"}}, "RobotStopped early entry at 299 s"),
    ("T", "D", "no-validation", {"sm_cls": V.NoValidationSM, "expect_error": "KeyError: 'ghost9'"},
     "unknown / ill-typed values not detected (crashes on the unregistered individual)"),
    ("T", "A", "no-guard", {"guard": False}, "unknown / ill-typed values not detected (A without the catalogue helper)"),
    ("X2", "D", "relation-only-check", {"context": V.relation_only(), "expect_error": "TYPE_MISMATCH"},
     "class compatibility limited to the subclass relation (refuses a valid Biped/Wheeled condition)"),
    ("B1", "A", "helper-boundary-lt", {"a_variant": "helper", "initial_map": {"initial-main-v1": "initial-main-strict"}},
     "helper A with a boundary error (< instead of <=)"),
    ("B2", "A", "helper-stale-model", {"a_variant": "helper", "skip_changes": True}, "helper A plan not updated"),
]


def run_one(out_dir, group, sid, arm, label, variant):
    path = os.path.join(out_dir, "raw", group, f"{sid}__{arm}__{label}.jsonl")
    rows = core_run.run(sc_path(sid) if isinstance(sid, str) else sid, arm, variant, path, label)
    return path, rows


def x1_runs(out_dir):
    with open(os.path.join(INPUTS, "expected", "X1-truth.yml")) as f:
        table = yaml.safe_load(f)
    res = []
    for robot, battery, yes in table["rows"]:
        # YAML 1.1 reads the yes / no of the independently written table as booleans
        if yes not in (True, False, "yes", "no"):
            raise ValueError(f"X1 row {robot} {battery}: {yes!r}")
        yes = "yes" if yes in (True, "yes") else "no"
        sid = f"X1-{robot}-{battery}"
        sc = {"id": sid, "d": {"model": "M1", "binding": "b-main"}, "a": {"initial": "initial-main-v1"},
              "observe": ["manager1"],
              "steps": [{"id": "x", "report": [robot, "RobotStatus", robot, {"battery": battery, "zone": "storage"}]}]}
        exp = {"calls": {"x": {"manager1": [["assert", "RobotStatus", robot, {"battery": battery, "zone": "storage"}]]}
                         if yes == "yes" else {}}, "no_positive_calls": yes == "no"}
        for arm, label, variant, kind in [("D", "main", {}, "main"), ("A", "main", {}, "main"),
                                          ("D", "dup-branch", {"sm_cls": V.DupBranchSM}, "negative")]:
            path = os.path.join(out_dir, "raw", "x1", f"{sid}__{arm}__{label}.jsonl")
            rows = core_run.run(sc, arm, variant, path, label)
            j = judge.judge(rows, exp, sc)
            res.append({"row": [robot, battery, yes], "arm": arm, "variant": label, "kind": kind,
                        "pass": j["pass"], "raw": os.path.relpath(path, out_dir),
                        "observed": rows[1]["calls"].get("manager1", []) if len(rows) > 2 else None})
    return res


def _dnf_of(consumers, pred):
    out = []
    for conj in consumers["probe1"][pred]:
        out.append([[c["field"], c["op"], (":" + c["value"][len(NS):]) if isinstance(c["value"], str)
                     and c["value"].startswith(NS) else c["value"]] for c in conj])
    return out


def grammar_cases():
    cat, types = core_run.catalogue()
    with open(os.path.join(INPUTS, "expected", "G-grammar.yml")) as f:
        cases = yaml.safe_load(f)["cases"]
    pattern = {"RobotStatus": "logistics:RobotStatus($robot, $battery, $zone)",
               "CargoCarriedBy": "logistics:CargoCarriedBy($cargo, $robot)",
               "BipedBalance": "logistics:BipedBalance($robot, $tilt)"}
    out = []
    for c in cases:
        blocks = [c["block"]] if "block" in c else [[c["twice"][0]], [c["twice"][1]]]
        reads = "".join(f"    {pattern[c['pred']]} {{\n" + "".join(f"      {l}\n" for l in b) + "    }\n" for b in blocks)
        text = ("prefix logistics: <http://ai.uos.ac.kr/logistics-ontology#>;\n\n"
                f"role Probe {{\n  reads {{\n{reads}  }}\n}}\n\n"
                "role Robot {\n  changes {\n    logistics:RobotStatus($robot, $battery, $zone);\n"
                "    logistics:CargoCarriedBy($cargo, $robot);\n    logistics:BipedBalance($robot, $tilt);\n  }\n}\n")
        got = {"stage": None, "codes": [], "dnf": None}
        try:
            spec = parse_org(text, cat)
            got["stage"] = "parsed"
            g = generate(spec, Binding("g", {"probe1": ["Probe"], "biped1": ["Robot"]}), types)
            got["stage"] = "generated"
            got["dnf"] = _dnf_of(g["consumers"], c["pred"])
        except OrgError as e:
            got["codes"] = [e.code]
            got["message"] = str(e)
        except GenerationError as e:
            got["codes"] = [f.code for f in e.findings]
            got["message"] = str(e)
        if "ok" in c:
            ok = got["dnf"] == c["ok"]
        else:
            ok = c["error"] in got["codes"]
        out.append({"id": c["id"], "note": c.get("note"), "text": text, "expected": c.get("ok", c.get("error")),
                    "observed": got, "pass": ok})
    return out


def a_static():
    cat, types = core_run.catalogue()
    sig = signature_of(cat, NS)
    with open(os.path.join(INPUTS, "expected", "A-static.yml")) as f:
        cases = yaml.safe_load(f)["cases"]
    rows = []
    for cid, text, want in cases:
        codes = [c for c, m in check_rule(text, sig, types)]
        rows.append({"id": cid, "rule": text, "expected": want, "observed": codes or ["ok"],
                     "pass": (codes == [] if want == "ok" else want in codes)})
    plans = {}
    for d in sorted(glob.glob(os.path.join(INPUTS, "models", "a*", "plans", "*")) +
                    glob.glob(os.path.join(INPUTS, "models", "a*", "contract", "plans", "*"))):
        if os.path.isdir(d):
            plans[os.path.relpath(d, INPUTS)] = check_plans(d, sig, types)
    d_models = {}
    for p in sorted(glob.glob(os.path.join(INPUTS, "models", "d", "**", "*.org"), recursive=True)):
        try:
            spec = parse_org(open(p).read(), cat)
            d_models[os.path.relpath(p, INPUTS)] = [f.to_dict() for f in check(spec, None, types) if f.severity == "error"]
        except OrgError as e:
            d_models[os.path.relpath(p, INPUTS)] = [{"code": e.code, "message": str(e)}]
    return {"cases": rows, "plan_dirs": plans, "d_models": d_models}


def git(repo, *args):
    try:
        return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception as e:                       # git missing inside a container
        return f"unavailable: {e}"


def manifest(out_dir, run_id, argv, t0, t1):
    files = {}
    for base in ("src", "runner", "inputs", "tools", "upstream", "run.sh", "expected-hashes.json"):
        for p in [os.path.join(ROOT, base)] + sorted(glob.glob(os.path.join(ROOT, base, "**", "*"), recursive=True)):
            if os.path.isfile(p) and "__pycache__" not in p:
                files[os.path.relpath(p, ROOT)] = sha(p)
    raw = {os.path.relpath(p, out_dir): sha(p) for p in sorted(glob.glob(os.path.join(out_dir, "raw", "**", "*.jsonl"), recursive=True))}
    try:
        import yaml as _y
        yv = _y.__version__
    except Exception:
        yv = None
    rcs = os.environ.get("CS_RCS") or os.path.join(ROOT, "..", "..", "..", "rcs-experiments")
    return {
        "run_id": run_id, "started": t0, "finished": t1,
        "command": " ".join(argv), "cwd": os.getcwd(),
        "environment": {"python": sys.version, "executable": sys.executable, "platform": platform.platform(),
                        "pyyaml": yv, "container": os.path.exists("/.dockerenv"),
                        "PYTHONDONTWRITEBYTECODE": os.environ.get("PYTHONDONTWRITEBYTECODE")},
        "upstream": json.load(open(os.path.join(ROOT, "upstream", "MANIFEST.json"))),
        "rcs_experiments_head": git(rcs, "rev-parse", "HEAD"),
        "rcs_experiments_status": git(rcs, "status", "--short"),
        "paper_repo_head": git(ROOT, "rev-parse", "HEAD"),
        "plan_code_sha256": sha(os.path.join(HERE, "plan.py")),
        "expected_hashes": json.load(open(os.path.join(ROOT, "expected-hashes.json"))),
        "snapshot": os.environ.get("CS_SNAPSHOT"),
        "files": files, "raw": raw,
        "raw_digest": hashlib.sha256("".join(f"{k}:{v}\n" for k, v in raw.items()).encode()).hexdigest(),
    }


def main():
    run_id = sys.argv[1]
    out_dir = os.path.join(ROOT, "results", run_id)
    if os.path.exists(out_dir):
        sys.exit(f"{out_dir} exists; results are never overwritten")
    os.makedirs(out_dir)
    t0 = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    judgments = []
    for sid in MAIN:
        for arm, label, variant in (("D", "main", {}), ("A", "main", {}), ("A", "helper", {"a_variant": "helper"})):
            path, rows = run_one(out_dir, "main", sid, arm, label, variant)
            with open(exp_path(sid)) as f:
                j = judge.judge(rows, yaml.safe_load(f), scenario_of(sid))
            judgments.append({"scenario": sid, "arm": arm, "variant": label, "kind": "main", "breaks": None,
                              "pass": j["pass"], "n_rows": j["n_rows"], "n_fail": j["n_fail"],
                              "expected_positive_calls": j["expected_positive_calls"],
                              "raw": os.path.relpath(path, out_dir), "expected": os.path.relpath(exp_path(sid), ROOT),
                              "failing": [r for r in j["rows"] if not r["ok"]]})
    for group, items, kind in (("contrast", CONTRASTS, "contrast"), ("negative", NEGATIVE, "negative")):
        for sid, arm, label, variant, breaks in items:
            path, rows = run_one(out_dir, group, sid, arm, label, variant)
            with open(exp_path(sid)) as f:
                j = judge.judge(rows, yaml.safe_load(f), scenario_of(sid))
            end = rows[-1] if rows and rows[-1].get("rec") == "end" else {}
            want_err = variant.get("expect_error")
            reason_ok = (want_err is not None and want_err in (end.get("error") or "")) or \
                        (want_err is None and not end.get("error"))
            judgments.append({"scenario": sid, "arm": arm, "variant": label, "kind": kind, "breaks": breaks,
                              "run_error": end.get("error"), "expect_error": want_err, "fails_for_declared_reason": reason_ok,
                              "pass": j["pass"], "n_rows": j["n_rows"], "n_fail": j["n_fail"],
                              "expected_positive_calls": j["expected_positive_calls"],
                              "raw": os.path.relpath(path, out_dir), "expected": os.path.relpath(exp_path(sid), ROOT),
                              "failing": [r for r in j["rows"] if not r["ok"]]})
    x1 = x1_runs(out_dir)
    grammar = grammar_cases()
    static = a_static()
    # audit: the judge is not a self-comparison and not vacuous
    audit = []
    with open(exp_path("B1")) as f:
        b1 = yaml.safe_load(f)
    empty = [{"rec": "start", "observe": ["manager1"]}] + \
            [{"rec": "step", "step": s, "calls": {}, "views": {}, "store": {}} for s in b1["calls"]] + [{"rec": "end"}]
    audit.append({"check": "empty observation fails B1", "ok": not judge.judge(empty, b1, scenario_of("B1"))["pass"]})
    audit.append({"check": "every main expected table has positive calls",
                  "ok": all(j["expected_positive_calls"] > 0 for j in judgments if j["kind"] == "main" and j["scenario"] != "CT7-cfg0"),
                  "note": "CT7-cfg0 is the removal control and expects no reception"})
    audit.append({"check": "every contrast / negative control ran to completion, or crashed with its declared error",
                  "ok": all(j["fails_for_declared_reason"] for j in judgments if j["kind"] != "main"),
                  "offenders": [f"{j['scenario']}:{j['arm']}:{j['variant']}" for j in judgments
                                if j["kind"] != "main" and not j["fails_for_declared_reason"]]})
    import ast
    with open(os.path.join(HERE, "judge.py")) as f:
        tree = ast.parse(f.read())
    mods = sorted({a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} |
                  {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module})
    audit.append({"check": "judge imports only the standard library and yaml (no arms / rcs / oracle / runner modules)",
                  "ok": set(mods) <= {"__future__", "json", "sys", "yaml"}, "imports": mods})
    pre = json.load(open(os.path.join(ROOT, "expected-hashes.json")))["files"]
    audit.append({"check": "expected tables equal the frozen expected-hashes.json record",
                  "ok": all(sha(os.path.join(ROOT, p)) == h for p, h in pre.items())
                  and sorted(pre) == sorted(os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(INPUTS, "expected", "**", "*.yml"), recursive=True))})
    nc = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "judge_mutation_nc.py"), out_dir],
                        capture_output=True, text=True)
    with open(os.path.join(out_dir, "judge_nc.stdout.txt"), "w") as f:
        f.write(nc.stdout + nc.stderr)
    audit.append({"check": "judge raw-mutation negative controls (tools/judge_mutation_nc.py) all as intended",
                  "ok": nc.returncode == 0})
    summary = {
        "run_id": run_id,
        "main": {"runs": sum(j["kind"] == "main" for j in judgments),
                 "pass": sum(j["kind"] == "main" and j["pass"] for j in judgments)},
        "contrast": {"runs": sum(j["kind"] == "contrast" for j in judgments),
                     "fail_as_intended": sum(j["kind"] == "contrast" and not j["pass"] for j in judgments)},
        "negative": {"runs": sum(j["kind"] == "negative" for j in judgments),
                     "fail_as_intended": sum(j["kind"] == "negative" and not j["pass"] for j in judgments)},
        "x1": {"rows": len({tuple(r["row"]) for r in x1}),
               "main_pass": sum(r["kind"] == "main" and r["pass"] for r in x1),
               "main_runs": sum(r["kind"] == "main" for r in x1),
               "dup_branch_rows_failing": sum(r["kind"] == "negative" and not r["pass"] for r in x1)},
        "grammar": {"cases": len(grammar), "pass": sum(g["pass"] for g in grammar)},
        "a_static": {"cases": len(static["cases"]), "pass": sum(c["pass"] for c in static["cases"]),
                     "plan_dirs_with_findings": [k for k, v in static["plan_dirs"].items() if v],
                     "d_models_with_errors": [k for k, v in static["d_models"].items() if v]},
        "audit": audit,
    }
    ok = (summary["main"]["runs"] == summary["main"]["pass"]
          and summary["contrast"]["runs"] == summary["contrast"]["fail_as_intended"]
          and summary["negative"]["runs"] == summary["negative"]["fail_as_intended"]
          and summary["x1"]["main_runs"] == summary["x1"]["main_pass"]
          and summary["x1"]["dup_branch_rows_failing"] > 0
          and summary["grammar"]["cases"] == summary["grammar"]["pass"]
          and summary["a_static"]["cases"] == summary["a_static"]["pass"]
          and all(a["ok"] for a in audit))
    summary["overall_ok"] = ok
    for name, obj in (("judgments", judgments), ("x1", x1), ("grammar", grammar), ("a_static", static),
                      ("summary", summary)):
        with open(os.path.join(out_dir, name + ".json"), "w") as f:
            json.dump(obj, f, indent=1, ensure_ascii=False, sort_keys=True, default=str)
    t1 = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest(out_dir, run_id, sys.argv, t0, t1), f, indent=1, ensure_ascii=False)
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
