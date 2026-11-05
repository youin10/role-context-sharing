"""Independent judge of one live run.

Inputs it trusts: the scenario input file (step schedule, observed roster, decider) and the
hand-written expected table (inputs/expected/...yml). The run's raw logs (logs/*.jsonl) and
manifest exit codes are the evidence. It imports nothing from src/, runner/ or cslive/ and
derives the roster and step list from the inputs, never from the raw (a raw that drops an
observer or a step cannot shrink what is checked).

Checks (each failure is listed in `problems` or as a mismatching row):
  roster      every expected process log exists with env/matched/final/exit, no error, exit 0
  steps       driver armed and settled [init] + scenario steps exactly once, in order; every
              worker received every arm in order; the end control message was sent
  calls       every non-decide step × observed agent: ordered calls equal the table ([] if absent)
  views/store/decisions/rejected   as listed in the table; views also rebuilt from calls only
  decisions   exactly one decision for every decide step
  messages    per topic and payload hash: every subscriber received each sent message exactly
              as often as it was sent (missing / duplicate / unsent receipts)
  causes      each call follows the inbox receipt that caused it; that payload was sent by a
              process on another host in the same step; D: the wire kind equals the call kind
              (assert / update / retract), report-caused assert / update and deletion retracts
              carry this step's event, model-change notifications carry the change's sequence
              (tr); A: update and report-caused assert come from a notify with this step's event,
              assert also from a match, deletion retracts from the tombstone notify, change-step
              calls from this step's load request or the notify / match it triggers
  python3 -I judge.py <run_dir> <d|a> <scenario.yml> <expected.yml> [out.json]   exit 0 = PASS
"""
import glob
import json
import os
import sys

import yaml


def read_logs(run_dir):
    logs = {}
    for p in sorted(glob.glob(os.path.join(run_dir, "logs", "*.jsonl"))):
        rows = []
        with open(p) as f:
            for line in f:
                if line.strip():
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        rows.append({"kind": "unparsable"})
        logs[os.path.basename(p)[:-6]] = rows
    return logs


def norm(v):
    return json.dumps(v, sort_keys=True)


def judge(run_dir, sc, exp, arm):
    logs = read_logs(run_dir)
    sid_all = ["init"] + [s["id"] for s in sc["steps"]]
    steps = {s["id"]: s for s in sc["steps"]}
    observed = list(sc.get("observe", []))
    ag = lambda a: f"{arm}-agent-{a}"                                   # noqa: E731
    center = "d-sm" if arm == "d" else "a-ltm"
    roster = ["driver", center, f"{arm}-producer"] + [ag(a) for a in observed]
    host_proc = lambda a: ag(a) if a in observed else f"{arm}-producer"  # noqa: E731
    problems, rows = [], []
    P = lambda what, **kw: problems.append({"what": what, **kw})      # noqa: E731

    # roster ---------------------------------------------------------------------------
    try:
        with open(os.path.join(run_dir, "manifest.json")) as f:
            exits = json.load(f).get("exit_codes", {})
    except (OSError, ValueError):
        exits = {}
        P("manifest_missing")
    host = {}
    for p in roster:
        rs = logs.get(p)
        if not rs:
            P("log_missing_or_empty", proc=p)
            continue
        kinds = [r.get("kind") for r in rs]
        for k in ("env", "matched", "final", "exit"):
            if kinds.count(k) != 1:
                P("lifecycle", proc=p, record=k, count=kinds.count(k))
        for r in rs:
            if r.get("kind") in ("error", "match_timeout", "ready_timeout", "step_timeout", "deadline_overrun",
                                 "unparsable"):
                P(r["kind"], proc=p, step=r.get("step"))
        host[p] = next((r.get("host") for r in rs if r.get("kind") == "env"), None)
        if exits.get(p) != 0:
            P("exit_code", proc=p, code=exits.get(p))
    for p in logs:
        if p not in roster:
            P("unexpected_process", proc=p)

    # steps ----------------------------------------------------------------------------
    drv = logs.get("driver", [])
    settled = [r.get("step") for r in drv if r.get("kind") == "settled"]
    if settled != sid_all:
        P("step_sequence", expected=sid_all, settled=settled)
    ctl = [json.loads(r["data"]) for r in drv if r.get("kind") == "tx" and r.get("topic") == "/cs/ctl"]
    armed = [c["step"]["id"] for c in ctl if c.get("phase") == "arm"]
    if armed != sid_all:
        P("arm_sequence", expected=sid_all, armed=armed)
    if sum(c.get("phase") == "end" for c in ctl) != 1:
        P("end_control", count=sum(c.get("phase") == "end" for c in ctl))
    for p in roster[1:]:
        got = [json.loads(r["data"])["step"]["id"] for r in logs.get(p, [])
               if r.get("kind") == "rx" and r.get("topic") == "/cs/ctl" and '"phase":"arm"' in r["data"]]
        if got != sid_all:
            P("worker_arm_sequence", proc=p, got=got)
    change_seq, change_rid = {}, {}
    for r in drv:
        if r.get("kind") == "generated":
            change_seq[r["step"]] = r["seq"]
        if r.get("kind") == "dispatch":
            change_rid[r["step"]] = r["request_id"]

    # calls ----------------------------------------------------------------------------
    calls = {}
    call_rows = []
    for a in observed:
        for r in logs.get(ag(a), []):
            if r.get("kind") == "call":
                if r.get("agent") != a or r.get("step") not in steps:
                    P("call_outside_steps", proc=ag(a), step=r.get("step"), agent=r.get("agent"))
                    continue
                calls.setdefault(r["step"], {}).setdefault(a, []).append([r["call"], r["c"], r["i"], r.get("v")])
                call_rows.append((ag(a), r))
    exp_calls = exp.get("calls") or {}
    for sid in sid_all[1:]:
        if steps[sid].get("decide"):
            if calls.get(sid):
                P("calls_on_decide_step", step=sid)
            continue
        for a in observed:
            want = (exp_calls.get(sid) or {}).get(a, [])
            got = calls.get(sid, {}).get(a, [])
            rows.append({"item": "calls", "step": sid, "agent": a, "ok": norm(want) == norm(got),
                         "want": want, "got": got})
    for sid in exp_calls:
        if sid not in steps:
            P("expected_step_not_in_input", step=sid)

    # views, store, decisions, rejected -------------------------------------------------
    def state_after(proc, sid):
        st = [r for r in logs.get(proc, []) if r.get("kind") == "state" and r.get("after") == sid]
        return st[-1] if len(st) == 1 else ({"_dup": True} if st else None)

    rebuilt = {a: {} for a in observed}
    for sid in sid_all[1:]:
        for a in observed:
            for kind, c, i, v in calls.get(sid, {}).get(a, []):
                if kind in ("assert", "update"):
                    rebuilt[a][f"{c}/{i}"] = v
                else:
                    rebuilt[a].pop(f"{c}/{i}", None)
            st = state_after(ag(a), sid)
            logged = None if st is None else st.get("views", {}).get(a)
            if st is None or logged is None:
                P("state_missing", proc=ag(a), step=sid)
            elif norm(logged) != norm(rebuilt[a]):
                P("view_inconsistent_with_calls", agent=a, step=sid, logged=logged, rebuilt=rebuilt[a])
            want = ((exp.get("views") or {}).get(sid) or {}).get(a, "__absent__")
            if want != "__absent__":
                rows.append({"item": "view", "step": sid, "agent": a, "ok": norm(want) == norm(logged),
                             "want": want, "got": logged})
    for sid, want in (exp.get("store") or {}).items():
        st = state_after(center, sid)
        got = None if st is None else st.get("store", {})
        for item, v in want.items():
            g = None if got is None else got.get(item)
            rows.append({"item": "store", "step": sid, "key": item, "ok": norm(v) == norm(g), "want": v, "got": g})
    decs = {}
    dec_proc = ag(sc["decider"]) if sc.get("decider") else None
    for r in logs.get(dec_proc, []) if dec_proc else []:
        if r.get("kind") == "decision":
            decs.setdefault(r.get("step"), []).append(r.get("decision"))
    for sid in sid_all[1:]:
        if steps[sid].get("decide"):
            if len(decs.get(sid, [])) != 1:
                P("decision_count", step=sid, count=len(decs.get(sid, [])))
    for sid, want in (exp.get("decisions") or {}).items():
        got = decs.get(sid, [None])[0]
        rows.append({"item": "decision", "step": sid, "ok": got is not None and norm(want) == norm(got),
                     "want": want, "got": got})
    rej = {}
    for r in logs.get(center, []):
        if r.get("kind") == "rejected":
            rej.setdefault(r.get("step"), []).extend(x["code"] for x in r["rejected"])
    for sid in sid_all[1:]:
        want = sorted(((exp.get("rejected") or {}).get(sid)) or [])
        got = sorted(rej.get(sid, []))
        if "rejected" in exp or got:
            if not steps[sid].get("decide"):
                rows.append({"item": "rejected", "step": sid, "ok": want == got, "want": want, "got": got})

    # message conservation -----------------------------------------------------------------
    inbox = "/d/inbox/" if arm == "d" else "/cs/a/to/"
    data_topics = {"/d/report", "/d/apply", "/d/ack", "/cs/a/ltm"}

    def subscribers(topic):
        if topic.startswith(inbox):
            return {host_proc(topic[len(inbox):]), "driver"}
        if topic == "/d/apply":
            return {"d-sm"}
        return {center, "driver"}

    tx, rx = {}, {}
    tx_rec = {}
    for p, rs in logs.items():
        for r in rs:
            t = r.get("topic", "")
            if not (t in data_topics or t.startswith(inbox)):
                continue
            if r.get("kind") == "tx":
                tx[(t, r["h"])] = tx.get((t, r["h"]), 0) + 1
                tx_rec.setdefault(r["h"], []).append((p, r))
            elif r.get("kind") == "rx":
                rx.setdefault(p, {})[(t, r["h"])] = rx.get(p, {}).get((t, r["h"]), 0) + 1
    msg = {"sent": sum(tx.values()), "missing": 0, "duplicate": 0, "unsent": 0}
    for (t, hh), n in tx.items():
        for s in subscribers(t):
            got = rx.get(s, {}).get((t, hh), 0)
            if got < n:
                msg["missing"] += n - got
            elif got > n:
                msg["duplicate"] += got - n
    for s, d in rx.items():
        for key in d:
            if key not in tx:
                msg["unsent"] += d[key]
    for k in ("missing", "duplicate", "unsent"):
        if msg[k]:
            P(f"message_{k}", count=msg[k])

    # causes ---------------------------------------------------------------------------------
    by_seq = {p: {r.get("seq"): r for r in rs} for p, rs in logs.items()}
    cz = {"calls": len(call_rows), "rx_ok": 0, "cross_host": 0, "same_step": 0, "version_ok": 0}
    for p, r in call_rows:
        sid, kind, a = r["step"], r["call"], r["agent"]
        cause = r.get("cause") or {}
        rxr = by_seq.get(p, {}).get(cause.get("rx_seq"))
        if not rxr or rxr.get("kind") != "rx" or rxr.get("h") != cause.get("h") or rxr.get("topic") != inbox + a \
                or rxr.get("seq", 0) >= r.get("seq", 0):
            P("call_without_cause_rx", proc=p, step=sid, call=kind)
            continue
        cz["rx_ok"] += 1
        senders = [(q, t) for q, t in tx_rec.get(cause["h"], []) if q != p and t.get("topic") == rxr["topic"]]
        if len(senders) != 1:
            P("cause_sender_count", proc=p, step=sid, call=kind, senders=len(senders))
            continue
        q, txr = senders[0]
        if host.get(q) and host.get(q) != host.get(p):
            cz["cross_host"] += 1
        else:
            P("cause_same_host", proc=p, sender=q, step=sid)
        if txr.get("step") == sid:
            cz["same_step"] += 1
        else:
            P("cause_other_step", proc=p, step=sid, sender_step=txr.get("step"), call=kind)
        m = json.loads(txr["data"])
        ok = True
        if arm == "d":
            ok = m.get("k") == kind
            if sid in change_seq:
                ok = ok and m.get("tr") is True and m.get("seq") == change_seq[sid]
            elif kind in ("assert", "update") or "e" in m:
                ok = ok and m.get("e") == f"{sc['id']}:{sid}"
        else:
            if sid in change_rid:
                ok = m.get("type") in ("load", "notify", "match") and \
                    (m.get("type") != "load" or m.get("request_id") == change_rid[sid])
            elif kind == "update":
                ok = m.get("type") == "notify" and m.get("env", {}).get("event_id") == f"{sc['id']}:{sid}"
            elif kind == "assert":
                ok = m.get("type") == "match" or \
                    (m.get("type") == "notify" and m.get("env", {}).get("event_id") == f"{sc['id']}:{sid}")
            elif m.get("type") == "notify" and m.get("env", {}).get("op") == "delete":
                ok = m.get("env", {}).get("event_id") == f"{sc['id']}:{sid}"
        if ok:
            cz["version_ok"] += 1
        else:
            P("cause_version", proc=p, step=sid, call=kind, cause=m)

    stats = {"expected_positive_calls": sum(len(c) for per in exp_calls.values() for c in (per or {}).values()),
             "observed_calls": len(call_rows),
             "by_kind": {k: sum(r["call"] == k for _, r in call_rows) for k in ("assert", "update", "retract")},
             "decisions": sum(len(v) for v in decs.values()), "rejected": sum(len(v) for v in rej.values()),
             "messages": msg, "causes": cz,
             "settle": [{"step": r.get("step"), "dt_s": r.get("dt_s"), "probes": r.get("probes")}
                        for r in drv if r.get("kind") == "settled"]}
    verdict = "PASS" if rows and all(r["ok"] for r in rows) and not problems else "FAIL"
    return {"schema": "cslive-judge/2", "verdict": verdict, "arm": arm, "scenario": sc["id"], "roster": roster,
            "hosts": host, "problems": problems, "compared": len(rows),
            "mismatches": [r for r in rows if not r["ok"]], "rows": rows, "stats": stats}


def main():
    run_dir, arm, sc_path, exp_path = sys.argv[1:5]
    out_path = sys.argv[5] if len(sys.argv) > 5 else os.path.join(run_dir, "judge.json")
    with open(sc_path) as f:
        sc = yaml.safe_load(f)
    with open(exp_path) as f:
        exp = yaml.safe_load(f)
    res = judge(run_dir, sc, exp, arm)
    with open(out_path, "w") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    print(json.dumps({"verdict": res["verdict"], "compared": res["compared"], "mismatches": len(res["mismatches"]),
                      "problems": [p["what"] for p in res["problems"]][:10], "stats": {
                          k: res["stats"][k] for k in ("expected_positive_calls", "observed_calls", "messages", "causes")}}))
    return 0 if res["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
