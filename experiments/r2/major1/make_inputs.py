"""Major 1 input generator (deterministic; written before any measurement).

Fixed: N=4 robots, K=4 consumers, binding c001..c004 -> [Mgr] (DUP: [MgrA, MgrB]),
r001..r004 -> [Robot]. Predicate logistics:RobotStatus($robot, $battery, $zone).

Line j of the OR family (k = j // 5, z_j = "z<j>") is `X_j || $zone != "z_j";` with X_j by j % 5:
  0  $robot == logistics:Biped (k even) / logistics:Humanoid (k odd)     class membership
  1  $battery <= 40+k                                                     battery upper bound
  2  $zone == "storage"                                                   zone equality
  3  $battery >= 20-k                                                     battery lower bound
  4  $robot != logistics:Wheeled (k even) / logistics:DifferentialDrive   class non-membership
Every line can be falsified alone (zone == z_j and X_j false; every other line holds through
its own `$zone != z_i`). The AND family is the same text with `||` replaced by `&&` (2m atoms,
one clause); all 2m atoms hold together for r001 (Humanoid), battery 30, zone "storage".

  python make_inputs.py <out_dir>
"""
import hashlib
import json
import os
import sys

PREFIX = "prefix logistics: <http://ai.uos.ac.kr/logistics-ontology#>;\n\n"
ROBOTS = {"r001": ["Humanoid"], "r002": ["DifferentialDrive"], "r003": ["Biped", "Wheeled"], "r004": ["Wheeled"]}
CONSUMERS = ["c001", "c002", "c003", "c004"]
OR_M = [1, 2, 4, 8, 10, 12, 14, 16, 18, 20]
DUP_M = [1, 2, 4, 8]


def atoms(j):
    """(X_j, Z_j) as structured atoms: (field, op, value); op 'isa'/'!isa' for classes."""
    k, t = j // 5, j % 5
    x = [("robot", "isa", "Biped" if k % 2 == 0 else "Humanoid"),
         ("battery", "<=", 40 + k),
         ("zone", "=", "storage"),
         ("battery", ">=", 20 - k),
         ("robot", "!isa", "Wheeled" if k % 2 == 0 else "DifferentialDrive")][t]
    return [list(x), ["zone", "!=", f"z{j}"]]


def atom_text(a):
    f, op, v = a
    if op in ("isa", "!isa"):
        return f"${f} {'==' if op == 'isa' else '!='} logistics:{v}"
    return f"${f} {'==' if op == '=' else op} {json.dumps(v)}"


def body(lines, joiner):
    return "".join(f"      {f' {joiner} '.join(atom_text(a) for a in line)};\n" for line in lines)


def role(name, lines_text):
    return (f"role {name} {{\n  reads {{\n    logistics:RobotStatus($robot, $battery, $zone) {{\n"
            f"{lines_text}    }}\n  }}\n}}\n")


ROBOT_ROLE = "role Robot {\n  changes {\n    logistics:RobotStatus($robot, $battery, $zone);\n  }\n}\n"
REF_LINES = [[["robot", "isa", "Biped"], ["battery", "<=", 30]], [["robot", "isa", "Wheeled"], ["battery", "<=", 20]]]


def config(family, m):
    if family == "REF":   # existing sweep condition: one line, (Biped && <=30) || (Wheeled && <=20)
        text = PREFIX + role("Mgr", "      $robot == logistics:Biped && $battery <= 30 || $robot == logistics:Wheeled && $battery <= 20;\n") + "\n" + ROBOT_ROLE
        formula = {"kind": "dnf", "clauses": REF_LINES}
        roles = ["Mgr"]
        exp = {"lines": 1, "atoms": 4, "expanded_reads_per_role": 2, "expanded_reads_total": 2,
               "final_alternatives_per_consumer": 2, "flows": 2}
    else:
        lines = [atoms(j) for j in range(m)]
        if family == "AND":
            text = PREFIX + role("Mgr", body(lines, "&&")) + "\n" + ROBOT_ROLE
            formula = {"kind": "and", "lines": lines}
            roles = ["Mgr"]
            exp = {"lines": m, "atoms": 2 * m, "expanded_reads_per_role": 1, "expanded_reads_total": 1,
                   "final_alternatives_per_consumer": 1, "flows": 1}
        elif family == "OR":
            text = PREFIX + role("Mgr", body(lines, "||")) + "\n" + ROBOT_ROLE
            formula = {"kind": "cnf2", "lines": lines}
            roles = ["Mgr"]
            exp = {"lines": m, "atoms": 2 * m, "expanded_reads_per_role": 2 ** m, "expanded_reads_total": 2 ** m,
                   "final_alternatives_per_consumer": 2 ** m, "flows": 2 ** m}
        elif family == "DUP":
            b = body(lines, "||")
            text = PREFIX + role("MgrA", b) + "\n" + role("MgrB", b) + "\n" + ROBOT_ROLE
            formula = {"kind": "cnf2", "lines": lines}
            roles = ["MgrA", "MgrB"]
            exp = {"lines": m, "atoms": 2 * m, "expanded_reads_per_role": 2 ** m, "expanded_reads_total": 2 * 2 ** m,
                   "final_alternatives_per_consumer": 2 ** m, "flows": 2 * 2 ** m}
        else:
            raise ValueError(family)
    binding = {**{c: roles for c in CONSUMERS}, **{r: ["Robot"] for r in ROBOTS}}
    return text, formula, binding, exp


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "individuals.ttl"), "w") as f:
        f.write("@prefix : <http://ai.uos.ac.kr/logistics-ontology#> .\n"
                + "".join(f":{r} a {' , '.join(':' + c for c in cs)} .\n" for r, cs in ROBOTS.items()))
    manifest = {"schema": "r2-major1-inputs/1", "robots": ROBOTS, "consumers": CONSUMERS, "configs": []}
    plan = [("REF", 0)] + [("OR", m) for m in OR_M] + [("AND", m) for m in OR_M] + [("DUP", m) for m in DUP_M]
    for family, m in plan:
        name = f"{family}-m{m:02d}"
        text, formula, binding, exp = config(family, m)
        with open(os.path.join(out, name + ".org"), "w") as f:
            f.write(text)
        with open(os.path.join(out, name + ".json"), "w") as f:
            json.dump({"family": family, "m": m, "formula": formula, "binding": binding, "expected": exp}, f, indent=1)
        manifest["configs"].append({"name": name, "family": family, "m": m, "expected": exp,
                                    "org_sha256": hashlib.sha256(text.encode()).hexdigest(),
                                    "org_bytes": len(text.encode())})
    files = sorted(p for p in os.listdir(out) if p != "MANIFEST.json")
    manifest["files"] = {p: hashlib.sha256(open(os.path.join(out, p), "rb").read()).hexdigest() for p in files}
    with open(os.path.join(out, "MANIFEST.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    print(len(manifest["configs"]), "configs written to", out)


if __name__ == "__main__":
    main()
