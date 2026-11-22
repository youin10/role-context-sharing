"""Independent semantics of the Major 1 input formulas (imports nothing from the core).

The formula is evaluated as written (lines AND-ed, alternatives within a line OR-ed), never
through a DNF expansion. Class membership uses its own closure written from
inputs/ontology/logistics-classes.ttl of the frozen core:
  Humanoid < Biped < Robot,  DifferentialDrive < Wheeled < Robot.
`!=` on a class: registered individual that is not a member (all test robots are registered).
"""
SUPER = {"Robot": {"Robot"}, "Biped": {"Biped", "Robot"}, "Humanoid": {"Humanoid", "Biped", "Robot"},
         "Wheeled": {"Wheeled", "Robot"}, "DifferentialDrive": {"DifferentialDrive", "Wheeled", "Robot"}}


def classes_of(robot_types, robot):
    out = set()
    for c in robot_types[robot]:
        out |= SUPER[c]
    return out


def atom(a, row, robot_types):
    f, op, v = a
    x = row[f]
    if op == "isa":
        return v in classes_of(robot_types, x)
    if op == "!isa":
        return v not in classes_of(robot_types, x)
    return {"=": x == v, "!=": x != v, "<": x < v, "<=": x <= v, ">": x > v, ">=": x >= v}[op]


def holds(formula, row, robot_types):
    k = formula["kind"]
    if k == "cnf2":     # every line: one of its alternatives
        return all(any(atom(a, row, robot_types) for a in line) for line in formula["lines"])
    if k == "and":      # every atom of every line
        return all(atom(a, row, robot_types) for line in formula["lines"] for a in line)
    if k == "dnf":      # some clause: all its atoms
        return any(all(atom(a, row, robot_types) for a in cl) for cl in formula["clauses"])
    raise ValueError(k)


def cases(formula, m, robot_types):
    """Grid of robots x battery set x zone set, then one falsifying and one boundary case per line."""
    ks = range(max(1, (m + 4) // 5)) if m else range(1)
    bat = sorted({0, 30, 100, 19, 20, 21, 29, 31} | {v for k in ks for v in (40 + k, 41 + k, 20 - k, 19 - k)})
    zones = ["storage", "yard", "z0"] + ([f"z{m - 1}"] if m > 1 else [])
    out = [(r, b, z, "grid") for r in sorted(robot_types) for b in bat for z in zones]
    if formula["kind"] in ("cnf2", "and"):
        for j, line in enumerate(formula["lines"]):
            f, op, v = line[0]
            z = f"z{j}"
            if op == "isa":           # a robot outside the class, and one inside it
                outside = [r for r in sorted(robot_types) if v not in classes_of(robot_types, r)]
                inside = [r for r in sorted(robot_types) if v in classes_of(robot_types, r)]
                out += [(outside[0], 30, z, f"line{j}-false"), (inside[0], 30, z, f"line{j}-true")]
            elif op == "!isa":
                inside = [r for r in sorted(robot_types) if v in classes_of(robot_types, r)]
                outside = [r for r in sorted(robot_types) if v not in classes_of(robot_types, r)]
                out += [(inside[0], 30, z, f"line{j}-false"), (outside[0], 30, z, f"line{j}-true")]
            elif op == "<=":
                out += [("r001", v + 1, z, f"line{j}-false"), ("r001", v, z, f"line{j}-true")]
            elif op == ">=":
                out += [("r001", v - 1, z, f"line{j}-false"), ("r001", v, z, f"line{j}-true")]
            elif op == "=":           # zone == storage: z_j != storage, so false
                out += [("r001", 30, z, f"line{j}-false"), ("r001", 30, "storage", f"line{j}-true")]
    return out
