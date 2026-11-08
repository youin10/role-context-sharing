"""Read-only access to the frozen conditional-sharing core (see setup.sh).

The core's class hierarchy and predicates are used unchanged. The simulator's zone individual is
added by loading one more individuals file; no core file is edited.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.environ.get("WCS_CORE") or os.path.abspath(os.path.join(HERE, "..", "core"))
EXTRA_INDIVIDUALS = os.path.join(HERE, "..", "config", "ontology", "simulator-individuals.ttl")
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(CORE, "runner"))

import api  # noqa: E402
import core_run  # noqa: E402
import variants  # noqa: E402
from arms.d.ontology import load_catalog, load_types  # noqa: E402

api._CAT = (load_catalog(os.path.join(api.INPUTS, "ontology", "predicates")),
            load_types(os.path.join(api.INPUTS, "ontology", "logistics-classes.ttl"),
                       os.path.join(api.INPUTS, "ontology", "logistics-individuals.ttl"),
                       EXTRA_INDIVIDUALS))

__all__ = ["CORE", "api", "core_run", "variants"]
