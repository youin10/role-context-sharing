"""Neutral information-needs table, assignment and configuration snapshots (spec §0.1).

The YAML files are the machine-readable twin of the neutral Markdown table handed to
the arm authors. Arm implementations must not read them (docs/interfaces.md §2).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

import yaml

OPS = ("=", "!=", "<", "<=", ">", ">=")
ORDERED_OPS = ("<", "<=", ">", ">=")


@dataclass(frozen=True)
class Cond:
    field: str
    op: str
    value: object

    def to_dict(self):
        return {"field": self.field, "op": self.op, "value": self.value}


@dataclass
class Read:
    context: str
    where: list[Cond] = field(default_factory=list)

    def to_dict(self):
        d = {"context": self.context}
        if self.where:
            d["where"] = [c.to_dict() for c in self.where]
        return d


@dataclass
class Context:
    name: str
    key: str
    fields: dict  # field -> "int" | "str" | "bool" | {"enum": [...]}
    text: str = ""

    def to_dict(self):
        return {"name": self.name, "key": self.key, "fields": self.fields, "text": self.text}


@dataclass
class Role:
    name: str
    reads: list[Read] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)
    text: str = ""

    def read_of(self, context):
        return next((r for r in self.reads if r.context == context), None)

    def to_dict(self):
        return {"name": self.name, "text": self.text,
                "reads": [r.to_dict() for r in self.reads], "changes": list(self.changes)}


@dataclass
class TaskKind:
    kind: str
    role: str
    step: str
    inputs: list[tuple[str, str]]  # (context, parameter name holding the instance id)
    deadline_s: float = 2.0
    text: str = ""

    def to_dict(self):
        return {"kind": self.kind, "role": self.role, "step": self.step,
                "inputs": [{"context": c, "instance": p} for c, p in self.inputs],
                "deadline_s": self.deadline_s, "text": self.text}


@dataclass
class Needs:
    domain: str
    contexts: list[Context]
    roles: list[Role]
    tasks: list[TaskKind] = field(default_factory=list)
    text: str = ""

    def context(self, name):
        return next(c for c in self.contexts if c.name == name)

    def role(self, name):
        return next(r for r in self.roles if r.name == name)

    def to_dict(self):
        return {"schema": "rcs-needs/1", "domain": self.domain, "text": self.text,
                "contexts": [c.to_dict() for c in self.contexts],
                "roles": [r.to_dict() for r in self.roles],
                "tasks": [t.to_dict() for t in self.tasks]}

    @staticmethod
    def from_dict(d):
        assert d.get("schema") == "rcs-needs/1", d.get("schema")
        return Needs(
            domain=d["domain"], text=d.get("text", ""),
            contexts=[Context(c["name"], c["key"], c["fields"], c.get("text", "")) for c in d["contexts"]],
            roles=[Role(r["name"],
                        [Read(x["context"], [Cond(**w) for w in x.get("where", [])]) for x in r.get("reads", [])],
                        list(r.get("changes", [])), r.get("text", "")) for r in d["roles"]],
            tasks=[TaskKind(t["kind"], t["role"], t["step"],
                            [(i["context"], i["instance"]) for i in t["inputs"]],
                            t.get("deadline_s", 2.0), t.get("text", "")) for t in d.get("tasks", [])])


@dataclass
class Assignment:
    agents: dict[str, list[str]]  # agent -> roles (ordered)

    def agents_of(self, role):
        return [a for a, rs in self.agents.items() if role in rs]

    def to_dict(self):
        return {"schema": "rcs-assignment/1",
                "agents": [{"agent": a, "roles": list(rs)} for a, rs in self.agents.items()]}

    @staticmethod
    def from_dict(d):
        assert d.get("schema") == "rcs-assignment/1", d.get("schema")
        return Assignment({x["agent"]: list(x["roles"]) for x in d["agents"]})


@dataclass
class Cfg:
    """One configuration version: needs table + assignment, identified by a common version ID."""
    cfg_id: str
    needs: Needs
    assignment: Assignment

    def to_dict(self):
        return {"schema": "rcs-cfg/1", "cfg_id": self.cfg_id,
                "needs": self.needs.to_dict(), "assignment": self.assignment.to_dict()}

    @staticmethod
    def from_dict(d):
        assert d.get("schema") == "rcs-cfg/1", d.get("schema")
        return Cfg(d["cfg_id"], Needs.from_dict(d["needs"]), Assignment.from_dict(d["assignment"]))

    def derive(self, cfg_id):
        return Cfg(cfg_id, copy.deepcopy(self.needs), copy.deepcopy(self.assignment))


def satisfies(where, value):
    """Field-constant AND over one instance value (harness-side helper for trace generation).
    The oracle implements its own evaluation (docs/interfaces.md §4)."""
    if value is None:
        return False
    for c in where:
        v = value.get(c.field)
        if c.op == "=" and not v == c.value:
            return False
        if c.op == "!=" and not v != c.value:
            return False
        if c.op == "<" and not v < c.value:
            return False
        if c.op == "<=" and not v <= c.value:
            return False
        if c.op == ">" and not v > c.value:
            return False
        if c.op == ">=" and not v >= c.value:
            return False
    return True


def validate(needs: Needs, assignment: Assignment | None = None):
    """Structural checks of the neutral table itself (not the D input checker F4)."""
    errs = []
    ctx = {c.name: c for c in needs.contexts}
    if len(ctx) != len(needs.contexts):
        errs.append("duplicate context name")
    roles = {r.name: r for r in needs.roles}
    for r in needs.roles:
        seen = set()
        for rd in r.reads:
            if rd.context not in ctx:
                errs.append(f"{r.name}: reads unknown context {rd.context}")
                continue
            if rd.context in seen:
                errs.append(f"{r.name}: duplicate read of {rd.context}")
            seen.add(rd.context)
            for c in rd.where:
                ftype = ctx[rd.context].fields.get(c.field)
                if ftype is None:
                    errs.append(f"{r.name}.{rd.context}: unknown field {c.field}")
                elif c.op not in OPS:
                    errs.append(f"{r.name}.{rd.context}: bad op {c.op}")
                elif c.op in ORDERED_OPS and ftype != "int":
                    errs.append(f"{r.name}.{rd.context}: ordered op on non-int field {c.field}")
        for ch in r.changes:
            if ch not in ctx:
                errs.append(f"{r.name}: changes unknown context {ch}")
    for t in needs.tasks:
        if t.role not in roles:
            errs.append(f"task {t.kind}: unknown role {t.role}")
        for c, _ in t.inputs:
            if c not in ctx:
                errs.append(f"task {t.kind}: unknown context {c}")
    if assignment:
        for a, rs in assignment.agents.items():
            for r in rs:
                if r not in roles:
                    errs.append(f"agent {a}: unknown role {r}")
    return errs


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


def dump_yaml(obj, path):
    with open(path, "w") as f:
        yaml.safe_dump(obj, f, sort_keys=False, allow_unicode=True, width=120)
