"""One Major 1 configuration in one process (launched by driver.py; run with python -B).

Timed calls (perf_counter, seconds), per repetition, on an in-memory org string as in
tools/sweep.py:
  F.parse     frozen arms.d.spec.parse_org(text, catalog)       whole parse incl. expansion
  F.check     frozen arms.d.checker.check(spec, binding, types)
  F.generate  frozen arms.d.generator.generate(spec, binding, types)   (runs check itself;
              never add F.check to it)
  I.parse     instrumented copy parse_org(text, catalog), with its internal spans
              I.product (line-combining statement only) and I.readdecl (ReadDecl list)
Order inside a repetition alternates: odd reps F.parse first, even reps I.parse first.
Rep 0 is the warm-up (recorded, excluded from statistics). After the timed reps (untimed):
identity of parse output and generated configuration between frozen and instrumented
copies, and the selection check through SMCore.report -> AgentCore -> App.calls against
the independent oracle. Every row is flushed immediately.

  python -B run_config.py <inputs dir> <name> <raw.jsonl> <reps> <per_call_s>
"""
import gc, hashlib, re, importlib.util, json, os, resource, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
from pathlib import Path

CORE = str(Path(__file__).resolve().parents[3] / "source" / "conditional-sharing")
sys.path[:0] = [os.path.join(CORE, "src"), os.path.join(CORE, "runner"), HERE]
import api  # noqa: E402
from arms.d.checker import check, errors  # noqa: E402
from arms.d.generator import generate  # noqa: E402
from arms.d.ontology import load_catalog, load_types  # noqa: E402
from arms.d.smcore import AgentCore, SMCore  # noqa: E402
from arms.d.spec import Binding, parse_org  # noqa: E402
import m1_oracle as oracle  # noqa: E402  (own module; core has src/oracle)

_s = importlib.util.spec_from_file_location("spec_instrumented", os.path.join(HERE, "instrumented", "spec_instrumented.py"))
INSTR = importlib.util.module_from_spec(_s)
sys.modules["spec_instrumented"] = INSTR
_s.loader.exec_module(INSTR)
pc = time.perf_counter


def canon(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def parse_digest(spec):
    return canon({r.name: [[rd.context, [[c.field, c.op, c.value] for c in rd.where], rd.alternative_group]
                           for rd in r.reads] for r in spec.roles.values()})


def selection(gen, formula, m, robot_types):
    """Feed every case as a report through the generated configuration and compare each
    consumer's App calls with the oracle-derived notification. Returns (summary, digest)."""
    sm = SMCore(gen)
    ac = {a: AgentCore() for a in gen["agents"]}
    apps = {a: api.App(a) for a in gen["agents"]}
    consumers = sorted(a for a in gen["consumers"] if gen["consumers"][a])
    prev, pv, log, mism = {}, {}, [], []
    kinds = {"assert": 0, "update": 0, "retract": 0, "none": 0}
    truth = {"true": 0, "false": 0}
    for n, (r, b, z, tag) in enumerate(oracle.cases(formula, m, robot_types), 1):
        val = {"battery": b, "zone": z}
        now = oracle.holds(formula, {"robot": r, **val}, robot_types)
        was = prev.get(r)
        truth["true" if now else "false"] += 1
        exp = (["update" if was else "assert", "RobotStatus", r, val] if now else
               (["retract", "RobotStatus", r, None] if was else None))
        kinds[exp[0] if exp else "none"] += 1
        before = {c: len(apps[c].calls) for c in consumers}
        pv[r] = pv.get(r, 0) + 1
        ev = {"schema": "rcs-env/1", "event_id": f"m1:{n}", "producer": r, "pv": {"n": pv[r], "ts": n},
              "context": "RobotStatus", "instance": r, "op": "upsert", "value": val}
        for a, msg in sm.report(ev):
            calls, ack = ac[a].handle(msg)
            for c in calls:
                getattr(apps[a], c[0])(*c[1:])
            if ack:
                sm.ack(a, ack)
        got = {c: apps[c].calls[before[c]:] for c in consumers}
        for c in consumers:
            if got[c] != ([exp] if exp else []):
                mism.append({"case": n, "tag": tag, "robot": r, "value": val, "consumer": c, "expected": exp, "got": got[c]})
        log.append([n, tag, r, b, z, now, exp[0] if exp else None])
        prev[r] = now
    summ = {"cases": len(log), "oracle_true": truth["true"], "oracle_false": truth["false"],
            "expected_kinds": kinds, "consumers": len(consumers), "mismatches": len(mism),
            "mismatch_examples": mism[:5], "sm_rejected": len(sm.rejected), "sm_stale": sm.stats["stale"],
            "line_false_cases": sum(1 for x in log if x[1].endswith("-false")),
            "line_false_cases_all_false": all(not x[5] for x in log if x[1].endswith("-false")) if formula["kind"] == "cnf2" else None}
    return summ, canon(log), canon({c: apps[c].calls for c in consumers})


def main():
    inp, name, raw_path, reps, per_call = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), float(sys.argv[5])
    meta = json.load(open(os.path.join(inp, name + ".json")))
    text = open(os.path.join(inp, name + ".org")).read()
    cat = load_catalog(os.path.join(CORE, "inputs", "ontology", "predicates"))
    types = load_types(os.path.join(CORE, "inputs", "ontology", "logistics-classes.ttl"), os.path.join(inp, "individuals.ttl"))
    binding = Binding("r2m1", meta["binding"])
    robot_types = {"r001": ["Humanoid"], "r002": ["DifferentialDrive"], "r003": ["Biped", "Wheeled"], "r004": ["Wheeled"]}
    raw = open(raw_path, "a")
    base = {"config": name, "family": meta["family"], "m": meta["m"], "pid": os.getpid()}

    def emit(row):
        raw.write(json.dumps({**base, **row}, sort_keys=True) + "\n")
        raw.flush()

    emit({"kind": "start", "gc_enabled": gc.isenabled(), "python": sys.version, "reps": reps, "per_call_s": per_call,
          "org_sha256": hashlib.sha256(text.encode()).hexdigest(), "t_wall": time.time()})
    for rep in range(0, reps + 1):
        T, spans = {}, {}

        def F():
            nonlocal specF
            t = pc(); specF = parse_org(text, cat); T["F.parse"] = pc() - t

        def I():
            INSTR.SPAN.update(product_s=0.0, product_calls=0, readdecl_s=0.0)
            t = pc(); INSTR.parse_org(text, cat); T["I.parse"] = pc() - t
            spans.update(INSTR.SPAN)
        specF = None
        order = ["F", "I"] if rep % 2 == 1 else ["I", "F"]
        stopped = None
        for step in order + ["check", "generate"]:
            if step == "F":
                F()
            elif step == "I":
                I()
            elif step == "check":
                t = pc(); fnd = check(specF, binding, types); T["F.check"] = pc() - t
            else:
                t = pc(); g = generate(specF, binding, types); T["F.generate"] = pc() - t
            over = [k for k, v in T.items() if v > per_call]
            if over:
                stopped = over
                break
        row = {"kind": "rep", "rep": rep, "warmup": rep == 0, "order": order, "times_s": T,
               "I.product_s": spans.get("product_s"), "I.product_calls": spans.get("product_calls"),
               "I.readdecl_s": spans.get("readdecl_s"), "maxrss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
        if stopped:
            emit({**row, "kind": "stopped", "reason": f"per_call_s {per_call} exceeded by {stopped}"})
            raw.close()
            return 3
        emit(row)
        if rep < reps:
            del g, fnd
            specF = None
    # untimed checks on the last repetition's objects -----------------------------
    exp = meta["expected"]
    reads = {r.name: len(r.reads) for r in specF.roles.values() if r.reads}
    final = {a: len(per["RobotStatus"]) for a, per in g["consumers"].items() if "RobotStatus" in per}
    INSTR.SPAN.update(product_s=0.0, product_calls=0, readdecl_s=0.0)
    specI = INSTR.parse_org(text, cat)
    gI = generate(specI, binding, types)
    selF = selection(g, meta["formula"], meta["m"], robot_types)
    selI = selection(gI, meta["formula"], meta["m"], robot_types)
    counts = {"atoms_in_text": len(re.findall(r"\$(?:robot|battery|zone)\s*(?:==|!=|<=|>=|<|>)", text)),
              "expanded_reads_per_role": reads, "expanded_reads_total": sum(reads.values()),
              "final_alternatives_per_consumer": final, "flows": len(g["flows"]),
              "check_errors": len(errors(fnd)), "check_warnings": len(fnd) - len(errors(fnd)),
              "I.product_calls": INSTR.SPAN["product_calls"]}
    ident = {"parse_digest_F": parse_digest(specF), "parse_digest_I": parse_digest(specI),
             "gen_digest_F": canon(g), "gen_digest_I": canon(gI),
             "selection_log_digest_F": selF[1], "selection_log_digest_I": selI[1],
             "selection_calls_digest_F": selF[2], "selection_calls_digest_I": selI[2]}
    ident["identical"] = (ident["parse_digest_F"] == ident["parse_digest_I"] and ident["gen_digest_F"] == ident["gen_digest_I"]
                          and selF[1] == selI[1] and selF[2] == selI[2])
    one = len(set(final.values())) == 1
    checks = {"identity": ident["identical"],
              "expanded_reads_per_role": all(v == exp["expanded_reads_per_role"] for v in reads.values()),
              "expanded_reads_total": sum(reads.values()) == exp["expanded_reads_total"],
              "final_alternatives_per_consumer": one and list(final.values())[0] == exp["final_alternatives_per_consumer"] and len(final) == 4,
              "flows": len(g["flows"]) == exp["flows"],
              "atoms": counts["atoms_in_text"] == exp["atoms"] * (2 if meta["family"] == "DUP" else 1),
              "no_check_errors": not errors(fnd),
              "selection_matches_oracle": selF[0]["mismatches"] == 0 and selF[0]["sm_rejected"] == 0 and selF[0]["sm_stale"] == 0,
              "oracle_has_true_and_false": selF[0]["oracle_true"] > 0 and selF[0]["oracle_false"] > 0}
    emit({"kind": "result", "expected": exp, "counts": counts, "identity": ident, "selection": selF[0],
          "checks": checks, "ok": all(checks.values()),
          "maxrss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, "t_wall": time.time()})
    raw.close()
    return 0 if all(checks.values()) else 4


if __name__ == "__main__":
    sys.exit(main())
