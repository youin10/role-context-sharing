"""Deterministic pose-to-cell mapping (config/topology.yml)."""
import yaml


class Topology:
    def __init__(self, path):
        with open(path) as f:
            doc = yaml.safe_load(f)
        self.x_bands = doc["x_bands"]
        self.y_bands = doc["y_bands"]

    def cell(self, x, y):
        for band in self.y_bands:
            lo, hi = band["range"]
            if lo <= y < hi:
                for (xlo, xhi), name in zip(self.x_bands, band["cells"]):
                    if xlo <= x < xhi:
                        return name
        raise ValueError(f"pose outside the map: ({x}, {y})")
