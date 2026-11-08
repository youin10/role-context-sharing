# Provenance

| Item | Origin |
|---|---|
| `vendor/cs-core-a255c156de6c.*` | Frozen core snapshot of https://github.com/youin10/role-context-sharing, byte-identical archive. `setup.sh` checks the SHA-256 and `tools/snapshot.py verify`. No core file is changed. |
| `LICENSE` | Same MIT license as that repository |
| Ontology | Classes, predicates and individuals of `core/inputs/ontology`, unchanged. `config/ontology/simulator-individuals.ttl` adds the individual `apron_zone` at load time |
| `sim/worlds/wcs.wbt` | New for this experiment, no PROTO assets |
| `sim/observer/observer.py`, `sim/carrier/carrier.py` | New for this experiment, written against the Webots Supervisor API |
| `wcs/`, `tools/`, `config/` | New for this experiment |

Base image `cyberbotics/webots:R2025a-ubuntu22.04@sha256:f0023e30daf38b172e4e6ad24ed345909bcd9551df34d63d824e121a7cebf099` (linux/amd64, emulated on arm64 hosts). The derived image `wcs-webots:R2025a` adds `python3-pip` and paho-mqtt 1.6.1; its local ID in the recorded runs is in each `manifest.json`. A rebuild can produce a different ID because the `apt-get` step is not pinned.

Recorded host: macOS on arm64, Docker 29.9.2, Compose 5.6.1, Python 3.14.7.

Source archive of the recorded runs: `snapshots/wcs-v2-522e80149f03.tar.gz`, SHA-256 `522e80149f03f5930f468f9aee3418bc4187d56c3f97e41d808bcd5b2711f07b`. It is reproducible with `tools/freeze_source.py`.
