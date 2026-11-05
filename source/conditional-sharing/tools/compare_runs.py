"""Re-run verification: compare raw logs and verdicts of several result directories.
Raw records are compared byte for byte, and again with the free-text traceback of an error
record removed (it contains absolute paths and interpreter-specific caret lines).

  python tools/compare_runs.py <out.json> results/<run> results/<run> ...
"""
import glob, hashlib, json, os, sys


def canon(path):
    out = []
    for line in open(path):
        r = json.loads(line)
        if r.get("rec") == "error":
            r["trace"] = r["trace"].strip().splitlines()[-1]       # keep only the exception line
        out.append(json.dumps(r, sort_keys=True))
    return hashlib.sha256("\n".join(out).encode()).hexdigest()


def verdicts(d):
    j = json.load(open(os.path.join(d, "judgments.json")))
    x = json.load(open(os.path.join(d, "x1.json")))
    g = json.load(open(os.path.join(d, "grammar.json")))
    return ({f"{r['kind']}:{r['scenario']}:{r['arm']}:{r['variant']}": r["pass"] for r in j} |
            {f"x1:{r['row'][0]}-{r['row'][1]}:{r['arm']}:{r['variant']}": r["pass"] for r in x} |
            {f"grammar:{r['id']}": r["pass"] for r in g})


out, dirs = sys.argv[1], sys.argv[2:]
base = dirs[0]
files = sorted(os.path.relpath(p, base) for p in glob.glob(os.path.join(base, "raw", "**", "*.jsonl"), recursive=True))
res = {"runs": dirs, "files": len(files), "pairs": []}
for d in dirs[1:]:
    byte = [f for f in files if open(os.path.join(base, f), "rb").read() != open(os.path.join(d, f), "rb").read()]
    sem = [f for f in files if canon(os.path.join(base, f)) != canon(os.path.join(d, f))]
    vb, vd = verdicts(base), verdicts(d)
    res["pairs"].append({"a": base, "b": d, "byte_different": byte, "different_after_trace_normalisation": sem,
                         "verdict_differences": sorted(k for k in vb.keys() | vd.keys() if vb.get(k) != vd.get(k)),
                         "missing_in_b": [f for f in files if not os.path.exists(os.path.join(d, f))]})
json.dump(res, open(out, "w"), indent=1)
print(json.dumps(res, indent=1))
