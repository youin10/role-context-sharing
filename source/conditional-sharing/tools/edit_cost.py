"""Edit cost of each change, computed from the versioned input files (D model / binding vs A plan
revision / dispatcher change list). Two lines per change: rules only, and rules + deployment list.
Also the one-time authoring size and the separately counted baseline helper code.

  python tools/edit_cost.py <out.json> <out-diff-dir>
"""
import difflib, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I = os.path.join(ROOT, "inputs", "models")


def lines(p):
    with open(os.path.join(I, p)) as f:
        return f.read().splitlines()


def diff(a, b, out_dir, name):
    d = list(difflib.unified_diff(lines(a) if a else [], lines(b), fromfile=a or "/dev/null", tofile=b, lineterm="", n=0))
    with open(os.path.join(out_dir, name + ".diff"), "w") as f:
        f.write("\n".join(d) + "\n")
    plus = sum(1 for l in d if l.startswith("+") and not l.startswith("+++"))
    minus = sum(1 for l in d if l.startswith("-") and not l.startswith("---"))
    return {"from": a, "to": b, "added": plus, "removed": minus, "changed_lines": max(plus, minus), "diff": name + ".diff"}


H = "a-helper/"
# Per change: D (org/binding diff + the apply request), A manual (plan diff + new changes file +
# the apply request), A helper (hand: config/assign diff + one spec.yml entry + apply request;
# generated: plan diff + changes file). Apply request = the change step of the scenario naming
# the new configuration (D: model+binding, A: change id); 1 line per arm.
CHANGES = {
    "C1": {"D_rules": [("d/M1.org", "d/M2.org")], "D_deploy": [],
           "A_rules": [("a/plans/v1/Manager.yml", "a/plans/v2/Manager.yml")], "A_deploy": [(None, "a/changes/C1.yml")],
           "H_hand": [(H + "config/v1.yml", H + "config/v2.yml")],
           "H_gen_rules": [(H + "plans/v1/Manager.yml", H + "plans/v2/Manager.yml")], "H_gen_deploy": [(None, H + "changes/C1.yml")]},
    "C2": {"D_rules": [("d/M2.org", "d/M1.org")], "D_deploy": [],
           "A_rules": [("a/plans/v2/Manager.yml", "a/plans/v1/Manager.yml")], "A_deploy": [(None, "a/changes/C2.yml")],
           "H_hand": [],
           "H_gen_rules": [(H + "plans/v2/Manager.yml", H + "plans/v1/Manager.yml")], "H_gen_deploy": [(None, H + "changes/C2.yml")]},
    "R1": {"D_rules": [], "D_deploy": [("d/b-res2.yml", "d/b-res1.yml")],
           "A_rules": [], "A_deploy": [(None, "a/changes/R1.yml")],
           "H_hand": [(H + "assign/res2.yml", H + "assign/res1.yml")], "H_gen_rules": [], "H_gen_deploy": [(None, H + "changes/R1.yml")]},
    "R2": {"D_rules": [], "D_deploy": [("d/b-res1.yml", "d/b-res0.yml")],
           "A_rules": [], "A_deploy": [(None, "a/changes/R2.yml")],
           "H_hand": [(H + "assign/res1.yml", H + "assign/res0.yml")], "H_gen_rules": [], "H_gen_deploy": [(None, H + "changes/R2.yml")]},
    "CT4-1": {"D_rules": [("d/contract/CT4-0.org", "d/contract/CT4-1.org")], "D_deploy": [],
              "A_rules": [("a/contract/plans/ct4-0/Manager.yml", "a/contract/plans/ct4-1/Manager.yml")],
              "A_deploy": [(None, "a/contract/changes/CT4-1.yml")],
              "H_hand": [(H + "config/ct4-0.yml", H + "config/ct4-1.yml")],
              "H_gen_rules": [(H + "contract/plans/ct4-0/Manager.yml", H + "contract/plans/ct4-1/Manager.yml")],
              "H_gen_deploy": [(None, H + "contract/changes/CT4-1.yml")]},
    "CT4-2": {"D_rules": [("d/contract/CT4-1.org", "d/contract/CT4-2.org")], "D_deploy": [],
              "A_rules": [("a/contract/plans/ct4-1/Manager.yml", "a/contract/plans/ct4-2/Manager.yml")],
              "A_deploy": [(None, "a/contract/changes/CT4-2.yml")],
              "H_hand": [(H + "config/ct4-1.yml", H + "config/ct4-2.yml")],
              "H_gen_rules": [(H + "contract/plans/ct4-1/Manager.yml", H + "contract/plans/ct4-2/Manager.yml")],
              "H_gen_deploy": [(None, H + "contract/changes/CT4-2.yml")]},
}
APPLY_REQUEST_LINES = 1
SPEC_ENTRY_LINES = 1      # one `changes/<id>: {from, to}` line in a-helper/spec.yml


def main():
    out, ddir = sys.argv[1], sys.argv[2]
    os.makedirs(ddir, exist_ok=True)
    res = {}
    for cid, c in CHANGES.items():
        row = {}
        for arm, rk, dk in (("D", "D_rules", "D_deploy"), ("A_manual", "A_rules", "A_deploy")):
            rules = [diff(a, b, ddir, f"{cid}-{arm}-rules-{k}") for k, (a, b) in enumerate(c[rk])]
            deploy = [diff(a, b, ddir, f"{cid}-{arm}-deploy-{k}") for k, (a, b) in enumerate(c[dk])]
            r = sum(x["changed_lines"] for x in rules)
            dpl = sum(x["changed_lines"] for x in deploy)
            row[arm] = {"rules_only_lines": r, "with_targets_lines": r + dpl,
                        "with_targets_and_apply_request_lines": r + dpl + APPLY_REQUEST_LINES,
                        "files_rules": rules, "files_deploy": deploy}
        hand = [diff(a, b, ddir, f"{cid}-A_helper-hand-{k}") for k, (a, b) in enumerate(c["H_hand"])]
        gr = [diff(a, b, ddir, f"{cid}-A_helper-genrules-{k}") for k, (a, b) in enumerate(c["H_gen_rules"])]
        gd = [diff(a, b, ddir, f"{cid}-A_helper-gendeploy-{k}") for k, (a, b) in enumerate(c["H_gen_deploy"])]
        h = sum(x["changed_lines"] for x in hand)
        row["A_helper"] = {"hand_lines": h + SPEC_ENTRY_LINES, "hand_with_apply_request_lines": h + SPEC_ENTRY_LINES + APPLY_REQUEST_LINES,
                           "generated_rules_lines": sum(x["changed_lines"] for x in gr),
                           "generated_targets_lines": sum(x["changed_lines"] - 1 for x in gd),  # minus GENERATED header
                           "files_hand": hand, "files_generated": gr + gd,
                           "note": "C2 reuses the existing v1 config (no config edit); hand = config/assign diff + spec entry"}
        res[cid] = row
    count = lambda p: sum(1 for l in lines(p) if l.strip() and not l.strip().startswith("#"))
    authoring = {
        "D_model_M1_nonblank_lines": count("d/M1.org"),
        "D_binding_main_lines": count("d/b-main.yml"),
        "A_plans_v1_nonblank_lines": sum(count(os.path.join("a/plans/v1", f)) for f in sorted(os.listdir(os.path.join(I, "a/plans/v1")))),
        "A_plans_v1_rules": sum(1 for f in sorted(os.listdir(os.path.join(I, "a/plans/v1"))) for l in lines(os.path.join("a/plans/v1", f)) if l.startswith("- (rule")),
        "A_initial_main_lines": count("a/initial-main-v1.yml"),
        "A_plan_revision_dir_files": len(os.listdir(os.path.join(I, "a/plans/v2"))),
        "note": "A deploys a plan revision directory; v2 copies the 7 unchanged role files (counted as file copies, not edits)",
    }
    src = os.path.join(ROOT, "src", "arms", "a")
    nb = lambda p: sum(1 for l in open(p) if l.strip())
    helpers = {"A_core_reimplementation(arms/a/core.py, not an edit cost)": nb(os.path.join(src, "core.py")),
               "A_catalogue_helper(arms/a/typed.py, one-time, baseline added function)": nb(os.path.join(src, "typed.py")),
               "A_expand_target_helper(arms/a/expand.py, one-time)": nb(os.path.join(src, "expand.py")),
               "A_helper_build_script(tools/build_a_helper.py, one-time)": nb(os.path.join(ROOT, "tools", "build_a_helper.py")),
               "A_helper_inputs_one_time(config v1 + assign main + spec.yml, nonblank non-comment)":
                   count(H + "config/v1.yml") + count(H + "assign/main.yml") + count(H + "spec.yml")}
    with open(os.path.join(ROOT, "inputs", "edit-units.yml")) as f:
        import yaml
        units = yaml.safe_load(f)
    json.dump({"changes": res, "semantic_units_hand_counted": units["changes"], "authoring": authoring,
               "helper_source_nonblank_lines": helpers}, open(out, "w"), indent=1)
    for cid, row in res.items():
        print(cid, "D", row["D"]["rules_only_lines"], row["D"]["with_targets_and_apply_request_lines"],
              "A_manual", row["A_manual"]["rules_only_lines"], row["A_manual"]["with_targets_and_apply_request_lines"],
              "A_helper hand", row["A_helper"]["hand_lines"], row["A_helper"]["hand_with_apply_request_lines"],
              "generated", row["A_helper"]["generated_rules_lines"], row["A_helper"]["generated_targets_lines"])


if __name__ == "__main__":
    main()
