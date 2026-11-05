"""Negative-control mutants. Each one breaks exactly one requirement on purpose; the judge must
report FAIL for it. Kept apart from src/ so the implementation under test is never modified."""
from __future__ import annotations

from arms.d.smcore import SMCore, satisfied


class _Types:
    """Type-registry wrapper used only for condition evaluation (report validation unchanged)."""

    def __init__(self, base, types_of):
        self.base, self._types_of = base, types_of

    def types_of(self, x):
        return self._types_of(self.base, x)


class NoRetractSM(SMCore):
    """Retract omission: the retract on a condition exit (data change) is dropped; the retract of a
    deleted source fact is kept."""

    def report(self, ev, journal=True):
        return [(a, m) for a, m in super().report(ev, journal) if not (m["k"] == "retract" and "e" not in m)]


class NonTransitiveSM(SMCore):
    """Subclass missing: class membership uses only the directly asserted rdf:type."""

    def _sat(self, inst, alts, c, i, value):
        t = _Types(inst.types, lambda b, x: set(b.individuals[x]))
        return satisfied(alts, value, i, inst.gen["keys"].get(c), t)


class SignatureOnlySM(SMCore):
    """Wrong-type reception: the argumentType signature (Robot) is mistaken for the individual's
    type, so every robot counts as every Robot subclass."""

    def _sat(self, inst, alts, c, i, value):
        robot = "http://ai.uos.ac.kr/logistics-ontology#Robot"
        t = _Types(inst.types, lambda b, x: {k for k in b.classes if b.is_subclass(k, robot)} or set(b.types_of(x)))
        return satisfied(alts, value, i, inst.gen["keys"].get(c), t)


class PerRoleRetractSM(SMCore):
    """Residual-support mistake: an item is retracted when any alternative that supported it is
    removed, even though another role still supports it."""

    def _diff(self, a, old, new, seq):
        batch = []
        ctxs = set(old.gen["consumers"].get(a, {})) | set(new.gen["consumers"].get(a, {}))
        for c in sorted(ctxs):
            ao, an = old.alts(a, c), new.alts(a, c)
            removed = [conj for conj in (ao or []) if conj not in (an or [])]
            for i, (val, eid) in sorted(self.store.get(c, {}).items()):
                was, now_ = self._sat(old, ao, c, i, val), self._sat(new, an, c, i, val)
                lost = any(self._sat(old, [conj], c, i, val) for conj in removed)
                if now_ and not was:
                    batch.append(self._msg(a, "assert", c=c, i=i, v=val, e=eid, seq=seq, tr=True))
                elif was and (not now_ or lost):
                    batch.append(self._msg(a, "retract", c=c, i=i, seq=seq, tr=True))
        return batch


class DupBranchSM(SMCore):
    """Duplicate notification: one assert / update per satisfied OR branch instead of one per report."""

    def report(self, ev, journal=True):
        out = []
        for a, m in super().report(ev, journal):
            out.append((a, m))
            if m["k"] in ("assert", "update"):
                alts = self.active.alts(a, m["c"]) or []
                n = sum(self._sat(self.active, [conj], m["c"], m["i"], m["v"]) for conj in alts)
                for _ in range(n - 1):
                    out.append(self._msg(a, m["k"], c=m["c"], i=m["i"], v=m["v"], e=m["e"]))
        return out


class NoValidationSM(SMCore):
    """Type/ID validation off: reports are not checked against the catalogue."""

    def _invalid(self, ev):
        return None


class relation_only:
    """Context manager: the checker's class compatibility falls back to the subclass relation
    only (the pre-2026-10-28-follow-up rule), which wrongly refuses `Biped` signature + `== Wheeled`."""

    def __enter__(self):
        from arms.d.ontology import TypeRegistry
        self._orig = TypeRegistry.compatible
        TypeRegistry.compatible = lambda s, a, b: s.is_subclass(a, b) or s.is_subclass(b, a)
        return self

    def __exit__(self, *exc):
        from arms.d.ontology import TypeRegistry
        TypeRegistry.compatible = self._orig
        return False
