"""Tabulates recorded runs from raw events: outcomes, arm equality, simulation and wall spans.

  summarize.py <label>
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def semantic(events):
    keep = []
    for e in events:
        r = e["rec"]
        if r == "report":
            keep.append(["report", e["context"], e["instance"], e["value"]])
        elif r == "notify":
            keep.append(["notify", e["agent"], e["kind"], e["instance"], e["value"]])
        elif r == "decision":
            keep.append(["decision", e["task"], e["outcome"], e["occupants"]])
        elif r == "command":
            keep.append(["command", e["robot"], e["task"]])
    return keep


def main():
    label = sys.argv[1]
    base = os.path.join(ROOT, "records", label)
    rows = []
    seqs = {}
    for name in sorted(os.listdir(base)):
        path = os.path.join(base, name, "events.jsonl")
        if not os.path.exists(path):
            continue
        with open(path) as f:
            ev = [json.loads(x) for x in f]
        with open(os.path.join(base, name, "judge.json")) as f:
            verdict = json.load(f)
        s = [e for e in ev if e["rec"] == "sample"]
        count = lambda rec: sum(e["rec"] == rec for e in ev)
        sem = semantic(ev)
        digest = hashlib.sha256(json.dumps(sem, sort_keys=True).encode()).hexdigest()[:12]
        parts = name.split("-")
        seqs.setdefault("-".join([parts[0]] + parts[3:]), set()).add(digest)
        rows.append({"run": name, "pass": verdict["pass"], "status": ev[-1].get("status"),
                     "fail_codes": sorted({x["code"] for x in verdict["fails"]}),
                     "samples": len(s), "reports": count("report"), "notifications": count("notify"),
                     "decisions": count("decision"), "commands": count("command"), "arrivals": count("arrived"),
                     "t_sim_end": s[-1]["t_sim"] if s else None, "t_wall_end": ev[-1]["t_wall"],
                     "semantic_sha": digest})
    out = {"label": label, "rows": rows, "distinct_semantic_sequences": {k: len(v) for k, v in seqs.items()}}
    with open(os.path.join(base, "tabulation.json"), "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
