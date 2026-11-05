"""Small scale / overhead sweep of the typed path (core, in-process, one shared host).

Dimensions: R robots (individuals; odd = Biped, even = Wheeled), M consumer agents, C condition
roles per consumer (role j: Biped <= 30-j OR Wheeled <= 20-j; union = Biped <= 30 OR Wheeled <= 20).
Workload per configuration, identical for D and A:
  4 rounds of reports, every robot once per round, interleaved by robot:
    Biped 31, 30, 29, 31     Wheeled 21, 20, 19, 25
  one redeploy: every role's Wheeled threshold +10 (20-j -> 30-j); wheeled robots at 25 enter.
Expected calls per consumer come from the closed form below (no implementation import):
  round 2: assert for every robot (condition entry), round 3: update (still inside), round 4:
  retract for every robot (condition exit), redeploy: assert for every Wheeled robot (instance order).
Phases: D parse, check, generate (includes its own check), SM events, redeploy (parse+generate
v2, then stage); A helper expansion v1+v2 and targets, initial plan load, events, redeploy
(dispatch). Times are perf_counter seconds on a shared host: environment-bound exploration, not
robot-scale performance.

  python tools/sweep.py <out_dir> [reps]
"""
import json, os, platform, statistics, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "runner"))
import api  # noqa: E402
from arms.a.core import AAgentCore, Bus, dispatch, fields_from_signature  # noqa: E402
from arms.a.expand import targets, write_plans  # noqa: E402
from arms.a.typed import GuardedLTM  # noqa: E402
from arms.d.checker import check  # noqa: E402
from arms.d.generator import generate  # noqa: E402
from arms.d.ontology import load_catalog, load_types, signature_of  # noqa: E402
from arms.d.smcore import AgentCore, SMCore  # noqa: E402
from arms.d.spec import Binding, parse_org  # noqa: E402

NS = api.NS
VALUES = [1, 4, 16, 64]
BASE = 4


def configs():
    out = []
    for dim in ("R", "M", "C"):
        for v in VALUES:
            c = {"R": BASE, "M": BASE, "C": BASE, dim: v}
            out.append(c)
    for v in (1, 16):                      # diagonal; 64^3 is outside the agreed small sweep
        out.append({"R": v, "M": v, "C": v})
    uniq = []
    for c in out:
        if c not in uniq:
            uniq.append(c)
    return uniq


def robots(R):
    return [(f"r{i:03d}", "Biped" if i % 2 else "Wheeled") for i in range(1, R + 1)]


def org(C, wheeled_base):
    roles = []
    for j in range(C):
        roles.append(f"role Mgr{j} {{\n  reads {{\n    logistics:RobotStatus($robot, $battery, $zone) {{\n"
                     f"      $robot == logistics:Biped && $battery <= {30 - j} || $robot == logistics:Wheeled && $battery <= {wheeled_base - j};\n"
                     "    }\n  }\n}\n")
    roles.append("role Robot {\n  changes {\n    logistics:RobotStatus($robot, $battery, $zone);\n  }\n}\n")
    return "prefix logistics: <http://ai.uos.ac.kr/logistics-ontology#>;\n\n" + "\n".join(roles)


def a_config(C, wheeled_base):
    return {"roles": {**{f"Mgr{j}": [
        {"context": "RobotStatus", "field": "robot", "class": "Biped", "conds": [["<=", "battery", 30 - j]]},
        {"context": "RobotStatus", "field": "robot", "class": "Wheeled", "conds": [["<=", "battery", wheeled_base - j]]}]
        for j in range(C)}, "Robot": []}}


def trace(rs):
    seq = {"Biped": [31, 30, 29, 31], "Wheeled": [21, 20, 19, 25]}
    ev, n = [], {}
    for k in range(4):
        for r, t in rs:
            n[r] = n.get(r, 0) + 1
            ev.append({"schema": "rcs-env/1", "event_id": f"sw:{k}:{r}", "producer": r, "pv": {"n": n[r], "ts": len(ev) + 1},
                       "context": "RobotStatus", "instance": r, "op": "upsert", "value": {"battery": seq[t][k], "zone": "storage"}})
    return ev


def expected(rs):
    seq = {"Biped": [31, 30, 29, 31], "Wheeled": [21, 20, 19, 25]}
    calls = []
    for k in range(4):
        for r, t in rs:
            if k == 1:      # 30 / 20 enter the condition: first supply
                calls.append(["assert", "RobotStatus", r, {"battery": seq[t][k], "zone": "storage"}])
            elif k == 2:    # 29 / 19 stay inside: supplied fact updated
                calls.append(["update", "RobotStatus", r, {"battery": seq[t][k], "zone": "storage"}])
            elif k == 3:    # 31 / 25 leave the condition
                calls.append(["retract", "RobotStatus", r, None])
    calls += [["assert", "RobotStatus", r, {"battery": 25, "zone": "storage"}] for r, t in sorted(rs) if t == "Wheeled"]
    return calls


def write_types(d, rs):
    p = os.path.join(d, "individuals.ttl")
    with open(p, "w") as f:
        f.write("@prefix : <http://ai.uos.ac.kr/logistics-ontology#> .\n" + "".join(f":{r} a :{t} .\n" for r, t in rs))
    return p


def run_d(cfg, d, cat, types, rs, consumers):
    T = {}
    agents = {**{c: [f"Mgr{j}" for j in range(cfg["C"])] for c in consumers}, **{r: ["Robot"] for r, _ in rs}}
    b = Binding("sweep", agents)
    t = time.perf_counter(); spec = parse_org(org(cfg["C"], 20), cat); T["parse"] = time.perf_counter() - t
    t = time.perf_counter(); f = check(spec, b, types); T["check"] = time.perf_counter() - t
    t = time.perf_counter(); g = generate(spec, b, types); T["generate"] = time.perf_counter() - t
    sm = SMCore(g)
    ac = {a: AgentCore() for a in g["agents"]}
    apps = {a: api.App(a) for a in g["agents"]}

    def handle(out):
        for a, m in out:
            calls, ack = ac[a].handle(m)
            for c in calls:
                getattr(apps[a], c[0])(*c[1:])
            if ack:
                sm.ack(a, ack)
        return len(out)
    ev = trace(rs)
    t = time.perf_counter(); msgs = sum(handle(sm.report(e)) for e in ev); T["events"] = time.perf_counter() - t
    t = time.perf_counter(); g2 = generate(parse_org(org(cfg["C"], 30), cat), b, types); T["redeploy_generate"] = time.perf_counter() - t
    t = time.perf_counter(); msgs2 = handle(sm.stage(1, g2, "C", 0.0)); T["redeploy_stage"] = time.perf_counter() - t
    counts = {"events": len(ev), "sm_messages_events": msgs, "sm_messages_redeploy": msgs2,
              "consumer_alternatives": sum(len(alts) for per in g["consumers"].values() for alts in per.values()),
              "flows": len(g["flows"]), "errors": len([x for x in f if x.severity == "error"])}
    return T, counts, {c: apps[c].calls for c in consumers}


def run_a(cfg, d, sig, types, rs, consumers):
    T = {}
    arm = os.path.join(d, "a")
    assign = {**{c: [f"Mgr{j}" for j in range(cfg["C"])] for c in consumers}, **{r: ["Robot"] for r, _ in rs}}
    t = time.perf_counter()
    write_plans(a_config(cfg["C"], 20), os.path.join(arm, "plans/v1"), sig, types)
    write_plans(a_config(cfg["C"], 30), os.path.join(arm, "plans/v2"), sig, types)
    tg = targets(assign, assign, os.path.join(arm, "plans/v1"), os.path.join(arm, "plans/v2"))
    T["helper_expand_targets"] = time.perf_counter() - t
    os.makedirs(os.path.join(arm, "changes"), exist_ok=True)
    with open(os.path.join(arm, "changes/C.yml"), "w") as f:
        json.dump({"plans": "plans/v2", "targets": tg}, f)     # JSON is valid YAML
    bus = Bus(); ltm = GuardedLTM(bus, sig, types); order = fields_from_signature(sig)
    apps = {a: api.App(a) for a in assign}
    ag = {a: AAgentCore(a, bus, apps[a], order, arm) for a in assign}
    t = time.perf_counter()
    for a, roles in assign.items():
        ag[a]._load({"request_id": 0, "cfg": "initial", "roles": roles, "plans": "plans/v1"})
    n0 = bus.pump(10**9); T["initial_load"] = time.perf_counter() - t
    ev = trace(rs)
    t = time.perf_counter(); n1 = 0
    for e in ev:
        ag[e["producer"]].emit(e)
        n1 += bus.pump(10**9)
    T["events"] = time.perf_counter() - t
    t = time.perf_counter(); dispatch(bus, arm, os.path.join(arm, "changes/C.yml"), 1, "C"); n2 = bus.pump(10**9)
    T["redeploy_dispatch"] = time.perf_counter() - t
    counts = {"events": len(ev), "bus_messages_initial": n0, "bus_messages_events": n1, "bus_messages_redeploy": n2,
              "subscriptions_final": len(ltm.subs),
              "consumer_rules_final": sum(len(rs_) for c in consumers for rs_ in ag[c].rules.values()),
              "ltm_notify": ltm.counts["notify"], "targets": len(tg), "rejected": len(ltm.rejected)}
    return T, counts, {c: apps[c].calls for c in consumers}


def main():
    out, reps = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 5
    os.makedirs(out, exist_ok=True)
    O = os.path.join(api.INPUTS, "ontology")
    cat = load_catalog(os.path.join(O, "predicates"))
    sig = signature_of(cat, NS)
    raw = open(os.path.join(out, "sweep-raw.jsonl"), "w")
    summary = []
    for cfg in configs():
        name = f"R{cfg['R']}-M{cfg['M']}-C{cfg['C']}"
        d = os.path.join(out, "inputs", name)
        os.makedirs(d, exist_ok=True)
        rs = robots(cfg["R"])
        consumers = [f"c{i:03d}" for i in range(1, cfg["M"] + 1)]
        types = load_types(os.path.join(O, "logistics-classes.ttl"), write_types(d, rs))
        with open(os.path.join(d, "model-v1.org"), "w") as f:
            f.write(org(cfg["C"], 20))
        with open(os.path.join(d, "model-v2.org"), "w") as f:
            f.write(org(cfg["C"], 30))
        exp = expected(rs)
        per = {"D": [], "A": []}
        for rep in range(1, reps + 1):
            for arm in ("D", "A"):
                fn = run_d if arm == "D" else run_a
                T, counts, calls = fn(cfg, d, cat if arm == "D" else sig, types, rs, consumers)
                correct = all(calls[c] == exp for c in consumers)
                row = {"config": name, "dims": cfg, "arm": arm, "rep": rep, "times_s": T, "counts": counts,
                       "expected_calls_per_consumer": len(exp), "consumers": len(consumers), "correct": correct}
                raw.write(json.dumps(row, sort_keys=True) + "\n")
                per[arm].append(row)
        summary.append({"config": name, "dims": cfg, "expected_calls_per_consumer": len(exp),
                        **{arm: {"correct_all_reps": all(r["correct"] for r in rows),
                                 "counts": rows[0]["counts"],
                                 "median_s": {k: statistics.median(r["times_s"][k] for r in rows) for k in rows[0]["times_s"]}}
                           for arm, rows in per.items()}})
        print(name, "D ok" if summary[-1]["D"]["correct_all_reps"] else "D BAD",
              "A ok" if summary[-1]["A"]["correct_all_reps"] else "A BAD",
              {k: round(v * 1e3, 2) for k, v in summary[-1]["D"]["median_s"].items()},
              {k: round(v * 1e3, 2) for k, v in summary[-1]["A"]["median_s"].items()}, flush=True)
    raw.close()
    env = {"python": sys.version, "platform": platform.platform(), "reps": reps, "cpu_count": os.cpu_count(),
           "container": os.path.exists("/.dockerenv"), "argv": sys.argv,
           "note": "shared host, other processes not controlled; times are environment-bound exploration"}
    json.dump({"environment": env, "configs": summary}, open(os.path.join(out, "sweep-summary.json"), "w"), indent=1)
    return 0 if all(s["D"]["correct_all_reps"] and s["A"]["correct_all_reps"] for s in summary) else 1


if __name__ == "__main__":
    sys.exit(main())
