#!/usr/bin/env bash
# Verifies and extracts the frozen core, builds the simulator image, creates the Python environment.
set -euo pipefail
cd "$(dirname "$0")"

CORE_ID=cs-core-a255c156de6c
(cd vendor && shasum -a 256 -c "$CORE_ID.tar.gz.sha256")
if [ ! -d core ]; then
  mkdir core
  tar -xzf "vendor/$CORE_ID.tar.gz" --strip-components=1 -C core
  mkdir core/snapshots
  cp "vendor/$CORE_ID.json" core/snapshots/
fi
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python -B core/tools/snapshot.py verify "$CORE_ID"
docker build --platform linux/amd64 -t "${WCS_IMAGE:-wcs-webots:R2025a}" sim
docker image inspect eclipse-mosquitto:2 >/dev/null 2>&1 || docker pull eclipse-mosquitto:2
