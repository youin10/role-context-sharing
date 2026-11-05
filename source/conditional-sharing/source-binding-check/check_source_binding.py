"""Targeted static check of the source / binding validation (R1-1, R4-M10, R5-5).

Separate from the frozen core experiment: this folder is outside the snapshot members
(src, runner, inputs, tools, upstream, ...), so `tools/snapshot.py verify` is unaffected.
The frozen code is imported read-only (runner/api.py catalogue, src/arms/d checker/generator/smcore);
nothing in it is modified. Expectations are in expected.yml and were written before running.

  .venv/bin/python -I source-binding-check/check_source_binding.py <run_id>

Writes source-binding-check/results/<run_id>/ (refuses to overwrite): result.json, manifest.json.
Exit 0 iff every case matches its expectation.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (os.path.join(ROOT, "src"), os.path.join(ROOT, "runner")):
    sys.path.insert(0, p)

import yaml  # noqa: E402
import api  # noqa: E402  (runner/api.py: shared catalogue loader, read-only)
from arms.d.checker import check, errors  # noqa: E402
from arms.d.generator import GenerationError, generate  # noqa: E402
from arms.d.smcore import SMCore  # noqa: E402
from arms.d.spec import load_binding, load_spec_org  # noqa: E402

INP = os.path.join(HERE, "inputs")


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load(model, binding, cat):
    return load_spec_org(os.path.join(INP, model), cat), load_binding(os.path.join(INP, binding))


def run_static(case, cat, types):
    spec, binding = load(case["model"], case["binding"], cat)
    findings = [f.to_dict() for f in check(spec, binding, types)]
    obs = {"findings": findings, "errors": [f for f in findings if f["severity"] == "error"]}
    try:
        gen = generate(spec, binding, types)
        obs["generated"] = True
        obs["producers"] = gen["producers"]
        obs["consumers"] = {a: sorted(cs) for a, cs in gen["consumers"].items() if cs}
        obs["consumer_conditions"] = {a: cs for a, cs in gen["consumers"].items() if cs}
    except GenerationError as e:
        obs["generated"] = False
        obs["generation_error"] = str(e)
    return obs


def judge_static(case, obs):
    why = []
    codes = [f["code"] for f in obs["errors"]]
    warn = [f["code"] for f in obs["findings"] if f["severity"] == "warning"]
    if case["expect"] == "refuse":
        if obs["generated"]:
            why.append("generated although refusal expected")
        for m in case.get("must_include", []):
            if not any(f["code"] == m["code"] and m["where_contains"] in (f["where"] + f["message"])
                       for f in obs["errors"]):
                why.append(f"missing error {m['code']} at {m['where_contains']}")
        for c in case.get("must_not_include_codes", []):
            if c in codes:
                why.append(f"unexpected error {c}")
    else:
        if not obs["generated"] or codes:
            why.append(f"refused although acceptance expected: {codes}")
        else:
            prod = {a: sorted(v) for a, v in obs["producers"].items()}
            if prod != {a: sorted(v) for a, v in case["producers"].items()}:
                why.append(f"producers {prod} != {case['producers']}")
            if obs["consumers"] != {a: sorted(v) for a, v in case["consumers"].items()}:
                why.append(f"consumers {obs['consumers']} != {case['consumers']}")
    extra_warn = [w for w in warn if w not in case.get("warnings_allowed", [])]
    if extra_warn:
        why.append(f"unexpected warnings {extra_warn}")
    return why


def run_revision(case, cat, types):
    """Same order as runner/core_run.py DRun.change: generate the revised configuration first,
    then stage it in the SM. A GenerationError means stage() is never called."""
    spec0, b0 = load(case["initial"]["model"], case["initial"]["binding"], cat)
    sm = SMCore(generate(spec0, b0, types))
    obs = {"initial_seq": sm.active.seq, "initial_cfg": sm.active.gen["cfg"]}
    spec1, b1 = load(case["revised"]["model"], case["revised"]["binding"], cat)
    sent = []
    try:
        gen1 = generate(spec1, b1, types)
        sent = sm.stage(1, gen1, case["id"], 0.0)
        obs["revised_generated"] = True
    except GenerationError as e:
        obs["revised_generated"] = False
        obs["generation_error"] = str(e)
        obs["error_codes"] = [f.code for f in e.findings]
    obs.update(active_seq=sm.active.seq, active_cfg=sm.active.gen["cfg"], messages_sent=len(sent),
               staged=sorted(sm.staged))
    return obs


def judge_revision(case, obs):
    why = []
    if obs["revised_generated"]:
        why.append("revised configuration generated although refusal expected")
    for k, v in case["after"].items():
        if obs.get(k) != v:
            why.append(f"{k}={obs.get(k)} expected {v}")
    return why


def main():
    run_id = sys.argv[1]
    out = os.path.join(HERE, "results", run_id)
    if os.path.exists(out):
        sys.exit(f"refusing to overwrite {out}")
    exp_path = os.path.join(HERE, "expected.yml")
    with open(exp_path) as f:
        expected = yaml.safe_load(f)
    cat, types = api.catalogue()
    rows = []
    for case in expected["cases"]:
        if case["expect"] == "refuse_revision":
            obs = run_revision(case, cat, types)
            why = judge_revision(case, obs)
        else:
            obs = run_static(case, cat, types)
            why = judge_static(case, obs)
        rows.append({"id": case["id"], "expect": case["expect"], "pass": not why, "why": why, "observed": obs})
        print(f"{case['id']:6s} expect={case['expect']:16s} {'PASS' if not why else 'FAIL ' + '; '.join(why)}")
    os.makedirs(out)
    with open(os.path.join(out, "result.json"), "w") as f:
        json.dump(rows, f, indent=1, ensure_ascii=False)
    used = ["source-binding-check/check_source_binding.py", "source-binding-check/expected.yml"] + \
        [f"source-binding-check/inputs/{n}" for n in sorted(os.listdir(INP))] + \
        ["src/arms/d/checker.py", "src/arms/d/generator.py", "src/arms/d/smcore.py", "src/arms/d/spec.py",
         "src/arms/d/ontology.py", "runner/api.py"] + \
        sorted(os.path.relpath(os.path.join(dp, n), ROOT) for dp, _, ns in os.walk(os.path.join(ROOT, "inputs", "ontology"))
               for n in ns)
    manifest = {
        "run_id": run_id,
        "finished": datetime.datetime.now().astimezone().isoformat(),
        "command": " ".join([os.path.relpath(sys.executable, ROOT), "-I"] + [os.path.relpath(os.path.abspath(sys.argv[0]), ROOT)] + sys.argv[1:]),
        "environment": {"python": sys.version, "platform": platform.platform(),
                        "pyyaml": yaml.__version__},
        "core_snapshot_expected": "cs-core-9ec4e836cb48 (verify before and after: see verify-*.txt)",
        "passed": sum(r["pass"] for r in rows), "cases": len(rows),
        "files": {p: sha(os.path.join(ROOT, p)) for p in used},
        "scope": "separate static check; not part of the 25 condition cases, 48 core runs or 66 ROS 2 runs",
    }
    with open(os.path.join(out, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    print(f"{manifest['passed']}/{manifest['cases']} -> {os.path.relpath(out, ROOT)}")
    sys.exit(0 if manifest["passed"] == manifest["cases"] else 1)


if __name__ == "__main__":
    main()
