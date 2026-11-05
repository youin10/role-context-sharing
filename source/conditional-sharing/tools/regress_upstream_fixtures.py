"""Regression: the modified D generator (no type registry) must reproduce every upstream
generated configuration byte for byte. Reads ../rcs-experiments read-only.

  python tools/regress_upstream_fixtures.py <rcs-experiments dir> <out.json>
"""
import glob, hashlib, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from arms.d.ontology import load_catalog
from arms.d.spec import load_binding, load_spec_org
from arms.d.generator import generate

root, out = sys.argv[1], sys.argv[2]
cat = load_catalog(os.path.join(root, "arms/d/ontology"))
rows = []
for org in sorted(glob.glob(os.path.join(root, "arms/d/fixtures/*/cfg*/roles.org"))):
    d = os.path.dirname(org)
    ref = os.path.join(os.path.dirname(d), "generated", os.path.basename(d) + ".json")
    if not os.path.exists(ref):
        rows.append({"org": os.path.relpath(org, root), "status": "no-reference"})
        continue
    gen = generate(load_spec_org(org, cat), load_binding(os.path.join(d, "binding.yml")))
    mine = json.dumps(gen, indent=1, ensure_ascii=False)
    theirs = open(ref).read()
    rows.append({"org": os.path.relpath(org, root), "status": "same" if mine == theirs else "DIFF",
                 "sha256": hashlib.sha256(theirs.encode()).hexdigest()})
summary = {"n": len(rows), "same": sum(r["status"] == "same" for r in rows),
           "diff": sum(r["status"] == "DIFF" for r in rows), "rows": rows}
json.dump(summary, open(out, "w"), indent=1)
print(summary["n"], summary["same"], summary["diff"])
sys.exit(0 if summary["diff"] == 0 and summary["n"] == summary["same"] else 1)
