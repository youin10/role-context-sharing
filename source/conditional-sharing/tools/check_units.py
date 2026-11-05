"""Small checks with independently written expectations for parts the scenario runs do not exercise:
type-file loading errors (cycle, undeclared class), and the aligned oracle condition evaluation
(oracle/core.py holds with the instance under the key and class conditions).

  python tools/check_units.py <out.json>
"""
import json, os, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from arms.d.ontology import load_types  # noqa: E402
from oracle.core import holds  # noqa: E402

NS = "http://ai.uos.ac.kr/logistics-ontology#"
HEAD = "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n@prefix : <%s> .\n" % NS
rows = []


def case(cid, fn, expected):
    try:
        got = fn()
    except Exception as e:
        got = f"error:{type(e).__name__}"
    rows.append({"id": cid, "expected": expected, "observed": got, "pass": got == expected})


def types_from(text):
    with tempfile.NamedTemporaryFile("w", suffix=".ttl", delete=False) as f:
        f.write(HEAD + text)
    try:
        t = load_types(f.name)
        return sorted(c[len(NS):] for c in t.types_of("x1")) if "x1" in t.individuals else "loaded"
    finally:
        os.unlink(f.name)


case("U01 subClassOf cycle refused", lambda: types_from(":A a rdfs:Class ; rdfs:subClassOf :B .\n:B a rdfs:Class ; rdfs:subClassOf :A .\n"), "error:ValueError")
case("U02 undeclared class of an individual refused", lambda: types_from(":A a rdfs:Class .\n:x1 a :Nope .\n"), "error:ValueError")
case("U03 transitive membership", lambda: types_from(":A a rdfs:Class .\n:B a rdfs:Class ; rdfs:subClassOf :A .\n:C a rdfs:Class ; rdfs:subClassOf :B .\n:x1 a :C .\n"), ["A", "B", "C"])
case("U04 multiple membership is a union", lambda: types_from(":A a rdfs:Class .\n:B a rdfs:Class .\n:x1 a :A , :B .\n"), ["A", "B"])

T = load_types(os.path.join(ROOT, "inputs/ontology/logistics-classes.ttl"), os.path.join(ROOT, "inputs/ontology/logistics-individuals.ttl"))
W = [{"field": "robot", "op": "isa", "value": NS + "Biped"}, {"field": "battery", "op": "<=", "value": 30}]
case("U05 oracle holds: humanoid1 30 under Biped<=30 (key visible)", lambda: holds(W, {"battery": 30}, "humanoid1", "robot", T), True)
case("U06 oracle holds: diff1 25 under Biped<=30", lambda: holds(W, {"battery": 25}, "diff1", "robot", T), False)
case("U07 oracle holds: identity on the key", lambda: holds([{"field": "robot", "op": "=", "value": "biped1"}], {"battery": 1}, "biped1", "robot", T), True)
case("U08 oracle holds without key keeps the old value-only behaviour", lambda: holds([{"field": "battery", "op": "<", "value": 30}], {"battery": 29}), True)
case("U09 oracle holds: !isa on a registered non-Biped", lambda: holds([{"field": "robot", "op": "!isa", "value": NS + "Biped"}], {"battery": 1}, "wheeled1", "robot", T), True)
case("U10 oracle holds: unregistered individual is not treated as a value", lambda: holds([{"field": "robot", "op": "!isa", "value": NS + "Biped"}], {"battery": 1}, "ghost9", "robot", T), "error:KeyError")

# Consumer knowledge notifications on paths the scenario runs do not exercise (duplicates,
# retransmission, restart resync), contract CT5 configuration; expectations follow the
# assert / update / retract contract, not implementation output.
sys.path.insert(0, os.path.join(ROOT, "runner"))
import api  # noqa: E402
from arms.d.smcore import AgentCore, SMCore  # noqa: E402

G = {k: api.d_generate({"model": "contract/CT5", "binding": f"contract/b-ct5-{k}"})[0] for k in (0, 1, 2)}
_n = {}


def ev(inst, battery, op="upsert"):
    _n[inst] = _n.get(inst, 0) + 1
    return {"schema": "rcs-env/1", "event_id": f"u:{inst}:{_n[inst]}", "producer": inst, "pv": {"n": _n[inst], "ts": len(_n) + sum(_n.values())},
            "context": "RobotStatus", "instance": inst, "op": op,
            "value": None if op == "delete" else {"battery": battery, "zone": "storage"}}


class Side:
    """manager1's AgentCore + application; feed() returns the application calls as kind:instance."""

    def __init__(self):
        self.core, self.app, self.last = AgentCore(), api.App("manager1"), []

    def feed(self, out, sm=None):
        got = []
        for a, m in out:
            if a != "manager1":
                if sm is not None and m["k"] == "commit":
                    sm.ack(a, m["seq"])
                continue
            self.last.append(m)
            calls, ack = self.core.handle(m)
            for name, *args in calls:
                getattr(self.app, name)(*args)
                got.append(f"{name[3:]}:{args[1]}")
            if ack and sm is not None:
                sm.ack("manager1", ack)
        return got


journal = []
sm, side = SMCore(G[0], journal=journal.append), Side()
case("N01 entry: first supply asserts", lambda: side.feed(sm.report(ev("biped1", 28))), ["assert:biped1"])
case("N02 supplied fact updated inside the condition", lambda: side.feed(sm.report(ev("biped1", 35))), ["update:biped1"])
case("N03 duplicate of the last message: no call", lambda: side.feed([("manager1", side.last[-1])]), [])
case("N04 exit retracts; the stored value stays", lambda: (side.feed(sm.report(ev("biped1", 45))), sm.store["RobotStatus"]["biped1"][0]["battery"]),
     (["retract:biped1"], 45))
case("N05 re-entry asserts again", lambda: side.feed(sm.report(ev("biped1", 38))), ["assert:biped1"])
case("N06 report outside the condition for an unsupplied fact: no call", lambda: side.feed(sm.report(ev("wheel1", 50))), [])
case("N07 redeploy that keeps the requirement (FleetMonitor remains): no call", lambda: side.feed(sm.stage(1, G[1], "u1", 0.0), sm), [])
case("N08 last role released: retract, stored value stays", lambda: (side.feed(sm.stage(2, G[2], "u2", 0.0), sm), sm.store["RobotStatus"]["biped1"][0]["battery"]),
     (["retract:biped1"], 38))
case("N09 retransmitted transition batch after it was applied: no call",
     lambda: side.feed([("manager1", m) for m in sm.batches.get((2, "manager1"), side.last[-2:])]), [])
case("N10 view after the release is empty", lambda: side.app.view(), {})

journal = []
sm, side = SMCore(G[1], journal=journal.append), Side()
side.feed(sm.report(ev("biped1", 28))); side.feed(sm.report(ev("hum1", 30)))
down = [{"r": ev("hum1", None, "delete")}, {"r": ev("wheel1", 20)}]      # reports replayed after the restart
sm2, _ = SMCore.recover(G[1], journal + down, 2, (lambda r: None), 0.0)
case("N11 restart resync: held fact updated, new eligible fact asserted, deleted held fact retracted",
     lambda: side.feed(sm2.snapshot()), ["update:biped1", "assert:wheel1", "retract:hum1"])
case("N12 view after resync", lambda: side.app.view(),
     {"RobotStatus/biped1": {"battery": 28, "zone": "storage"}, "RobotStatus/wheel1": {"battery": 20, "zone": "storage"}})


def a_dup():
    import core_run
    sc = api.load_scenario(os.path.join(ROOT, "inputs/scenarios/contract/CT5.yml"))
    r = core_run.ARun(sc, {})
    r.start()
    e = api.envelope(sc, api.steps(sc)[1], 1, 1)
    r.report(e)
    first = list(r.apps["manager1"].calls)
    r.agents["manager1"].receive({"type": "notify", "env": e})      # duplicate LTM notification
    r.bus.pump()
    return [c[0] for c in first], [c[0] for c in r.apps["manager1"].calls]


case("N13 A: duplicate notify of the same report changes nothing", a_dup, (["assert"], ["assert"]))
json.dump(rows, open(sys.argv[1], "w"), indent=1)
for r in rows:
    print("PASS" if r["pass"] else "FAIL", r["id"], r["observed"])
sys.exit(0 if all(r["pass"] for r in rows) else 1)
