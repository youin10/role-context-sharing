"""Major 3 auxiliary: per-round processing time of the normal report sequence, 4/4/4 (N/K/Q =
R/M/C = 4/4/4), D and A, state kept across the four rounds within one instance.

Workload, setup and the per-event loop are those of the frozen tools/sweep.py (imported
read-only): trace(rs) = 4 rounds x R reports, interleaved by robot
(Biped 31, 30, 29, 31; Wheeled 21, 20, 19, 25). Round k = events[k*R:(k+1)*R].
Expected application calls per consumer per round (sweep.expected without its redeploy tail):
  round 1 none (31/21 outside the condition), round 2 assert (30/20 enter),
  round 3 update (29/19 stay inside), round 4 retract (31/25 leave).
Timed region per round = the sweep `events` loop body restricted to that round:
  D  for e in round: handle(sm.report(e))   (SM routing + AgentCore + App calls + acks)
  A  for e in round: ag[producer].emit(e); bus.pump(10**9)
Setup (parse/check/generate + SM/agents for D; plan expansion + initial load for A) is untimed.
Modes, each on a fresh instance: split (4 timers, one per round) and whole (one timer over the
same 16 events, as sweep `events`). Order of (arm, mode) cells alternates ABBA per repetition.
Rep 0 is warm-up (recorded, excluded from statistics).

  python -B run_rounds.py <out_dir> [reps]
"""
import importlib.util, json, os, platform, sys, time

from pathlib import Path

CORE = str(Path(__file__).resolve().parents[3] / "source" / "conditional-sharing")
_s = importlib.util.spec_from_file_location("sweep", os.path.join(CORE, "tools", "sweep.py"))
sweep = importlib.util.module_from_spec(_s)
sys.modules["sweep"] = sweep
_s.loader.exec_module(sweep)
api = sweep.api
pc = time.perf_counter
CFG = {"R": 4, "M": 4, "C": 4}


def setup_d(env):
    cat, types, rs, consumers = env["cat"], env["types"], env["rs"], env["consumers"]
    agents = {**{c: [f"Mgr{j}" for j in range(CFG["C"])] for c in consumers}, **{r: ["Robot"] for r, _ in rs}}
    g = sweep.generate(sweep.parse_org(sweep.org(CFG["C"], 20), cat), sweep.Binding("sweep", agents), types)
    sm = sweep.SMCore(g)
    ac = {a: sweep.AgentCore() for a in g["agents"]}
    apps = {a: api.App(a) for a in g["agents"]}
    n = {"msgs": 0}

    def step(e):
        out = sm.report(e)
        for a, m in out:
            calls, ack = ac[a].handle(m)
            for c in calls:
                getattr(apps[a], c[0])(*c[1:])
            if ack:
                sm.ack(a, ack)
        n["msgs"] += len(out)
    probe = lambda: {"msgs": n["msgs"], **{k: sm.stats[k] for k in ("reports", "assert", "update", "retract", "stale", "rejected")}}
    return step, apps, probe


def setup_a(env, tag):
    sig, types, rs, consumers = env["sig"], env["types"], env["rs"], env["consumers"]
    arm = os.path.join(env["work"], f"a-{tag}")
    assign = {**{c: [f"Mgr{j}" for j in range(CFG["C"])] for c in consumers}, **{r: ["Robot"] for r, _ in rs}}
    sweep.write_plans(sweep.a_config(CFG["C"], 20), os.path.join(arm, "plans/v1"), sig, types)
    bus = sweep.Bus(); ltm = sweep.GuardedLTM(bus, sig, types); order = sweep.fields_from_signature(sig)
    apps = {a: api.App(a) for a in assign}
    ag = {a: sweep.AAgentCore(a, bus, apps[a], order, arm) for a in assign}
    for a, roles in assign.items():
        ag[a]._load({"request_id": 0, "cfg": "initial", "roles": roles, "plans": "plans/v1"})
    bus.pump(10**9)
    n = {"msgs": 0}

    def step(e):
        ag[e["producer"]].emit(e)
        n["msgs"] += bus.pump(10**9)
    probe = lambda: {"msgs": n["msgs"], **{k: ltm.counts[k] for k in ("notify", "match", "assert")}, "rejected": len(ltm.rejected)}
    return step, apps, probe


def run(env, arm, mode, tag):
    step, apps, probe = setup_d(env) if arm == "D" else setup_a(env, tag)
    ev, R, consumers = env["ev"], CFG["R"], env["consumers"]
    rounds = [ev[k * R:(k + 1) * R] for k in range(4)]
    T, per = [], []
    if mode == "split":
        for k in range(4):
            c0, p0 = {c: len(apps[c].calls) for c in consumers}, probe()
            t = pc()
            for e in rounds[k]:
                step(e)
            T.append(pc() - t)
            p1 = probe()
            per.append({"calls": {c: apps[c].calls[c0[c]:] for c in consumers},
                        "probe_delta": {x: p1[x] - p0[x] for x in p1}})
    else:
        p0 = probe()
        t = pc()
        for e in ev:
            step(e)
        T.append(pc() - t)
        p1 = probe()
        per.append({"calls": {c: list(apps[c].calls) for c in consumers}, "probe_delta": {x: p1[x] - p0[x] for x in p1}})
    return T, per


def expected_rounds(rs):
    exp = sweep.expected(rs)            # rounds 2..4 then the redeploy tail (excluded)
    R = len(rs)
    return [[], exp[0:R], exp[R:2 * R], exp[2 * R:3 * R]]


def main():
    out = sys.argv[1]
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    os.makedirs(out, exist_ok=True)
    work = os.path.join(out, "work")
    os.makedirs(work, exist_ok=True)
    O = os.path.join(sweep.api.INPUTS, "ontology")
    cat = sweep.load_catalog(os.path.join(O, "predicates"))
    rs = sweep.robots(CFG["R"])
    env = {"cat": cat, "sig": sweep.signature_of(cat, sweep.NS), "rs": rs, "work": work,
           "consumers": [f"c{i:03d}" for i in range(1, CFG["M"] + 1)],
           "types": sweep.load_types(os.path.join(O, "logistics-classes.ttl"), sweep.write_types(work, rs)),
           "ev": sweep.trace(rs)}
    expr = expected_rounds(rs)
    assert [c[0] for c in expr[1]] == ["assert"] * 4 and [c[0] for c in expr[2]] == ["update"] * 4 \
        and [c[0] for c in expr[3]] == ["retract"] * 4, "expected round kinds"
    json.dump({"events": env["ev"], "expected_per_consumer_by_round": expr, "robots": rs, "consumers": env["consumers"]},
              open(os.path.join(out, "workload.json"), "w"), indent=1)
    raw = open(os.path.join(out, "rows.jsonl"), "w")
    cells = [("D", "split"), ("D", "whole"), ("A", "split"), ("A", "whole")]
    for rep in range(0, reps + 1):
        order = cells if rep % 2 == 0 else cells[::-1]
        for arm, mode in order:
            T, per = run(env, arm, mode, f"{rep}-{mode}")
            if mode == "split":
                ok = [all(per[k]["calls"][c] == expr[k] for c in env["consumers"]) for k in range(4)]
            else:
                full = [x for k in range(4) for x in expr[k]]
                ok = [all(per[0]["calls"][c] == full for c in env["consumers"])]
            row = {"rep": rep, "warmup": rep == 0, "arm": arm, "mode": mode, "order": [f"{a}-{m}" for a, m in order],
                   "times_s": T, "per": per, "matches_expected": ok, "t_wall": time.time()}
            raw.write(json.dumps(row, sort_keys=True) + "\n")
            raw.flush()
    raw.close()
    ci = time.get_clock_info("perf_counter")
    json.dump({"python": sys.version, "platform": platform.platform(), "reps": reps, "warmup": 1, "cfg": CFG,
               "perf_counter": {"implementation": ci.implementation, "resolution": ci.resolution, "monotonic": ci.monotonic},
               "argv": sys.argv, "core": CORE, "sweep_py": os.path.join(CORE, "tools", "sweep.py")},
              open(os.path.join(out, "environment.json"), "w"), indent=1)
    print("done", out)


if __name__ == "__main__":
    main()
