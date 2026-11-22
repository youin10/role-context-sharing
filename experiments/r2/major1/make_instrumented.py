"""Create the separate instrumented copy of the frozen spec.py (only this file is copied).

Two spans are added inside OrgParser.pattern, nothing else changes:
  product_s   the line-combining statement `alts = [a + b for a in alts for b in line]`
              (the Cartesian expansion of one condition line into the clauses so far);
              excludes tokenizing and parsing the line itself (`self.line(bound)`)
  readdecl_s  building the ReadDecl list from the expanded clauses
Spans accumulate in module-level SPAN across every pattern of one parse call.

  python make_instrumented.py <frozen spec.py> <out dir>
"""
import difflib, hashlib, os, sys

src, out = sys.argv[1], sys.argv[2]
text = open(src).read()
A = "                alts = [a + b for a in alts for b in line]\n"
B = "        return [ReadDecl(name, a, None, self.group) for a in alts]\n"
assert text.count(A) == 1 and text.count(B) == 1, "anchor statements not unique"
new = text.replace(A, "                _t0 = _pc()\n" + A +
                   "                SPAN['product_s'] += _pc() - _t0\n                SPAN['product_calls'] += 1\n")
new = new.replace(B, "        _t1 = _pc()\n        _out = [ReadDecl(name, a, None, self.group) for a in alts]\n"
                     "        SPAN['readdecl_s'] += _pc() - _t1\n        return _out\n")
head = "import yaml\n"
assert new.count(head) == 1
new = new.replace(head, head + "from time import perf_counter as _pc\n"
                  "SPAN = {'product_s': 0.0, 'product_calls': 0, 'readdecl_s': 0.0}  # instrumentation (r2 major1)\n")
os.makedirs(out, exist_ok=True)
open(os.path.join(out, "spec_instrumented.py"), "w").write(new)
diff = "".join(difflib.unified_diff(text.splitlines(True), new.splitlines(True), "frozen/src/arms/d/spec.py", "instrumented/spec_instrumented.py"))
open(os.path.join(out, "spec.diff"), "w").write(diff)
open(os.path.join(out, "HASHES.txt"), "w").write(
    f"frozen spec.py sha256 {hashlib.sha256(text.encode()).hexdigest()}\n"
    f"instrumented sha256 {hashlib.sha256(new.encode()).hexdigest()}\n")
print(diff)
