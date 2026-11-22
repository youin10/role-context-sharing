import cProfile, pstats, sys, os, json
from pathlib import Path

CORE = str(Path(__file__).resolve().parents[4] / "source" / "conditional-sharing")
sys.path[:0]=[CORE+"/src"]
from arms.d.checker import check; from arms.d.generator import generate
from arms.d.ontology import load_catalog, load_types; from arms.d.spec import Binding, parse_org
inp="inputs"; name=sys.argv[1]
meta=json.load(open(f"{inp}/{name}.json")); text=open(f"{inp}/{name}.org").read()
cat=load_catalog(CORE+"/inputs/ontology/predicates"); types=load_types(CORE+"/inputs/ontology/logistics-classes.ttl", inp+"/individuals.ttl")
b=Binding("x", meta["binding"]); spec=parse_org(text,cat)
for fn in (lambda: check(spec,b,types), lambda: generate(spec,b,types)):
    p=cProfile.Profile(); p.enable(); fn(); p.disable(); pstats.Stats(p).sort_stats("cumtime").print_stats(8)
