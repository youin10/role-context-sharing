#!/usr/bin/env bash
# DDS ping smoke: two containers (ping, pong) on a fresh labelled bridge network with a unique
# ROS_DOMAIN_ID. Removes only the containers and network it created. Preparation, not a result.
#   bash smoke/run_ping.sh [N]
set -euo pipefail
cd "$(dirname "$0")/.."
N=${1:-50}
IMG=rcs-experiments:jazzy
RID=smoke-$(date +%Y%m%d-%H%M%S)
OUT=runs/$RID
DOM=$(( 100 + RANDOM % 100 ))
NET=cslive-$RID
mkdir -p "$OUT"
cleanup() {
  docker rm -f "cslive-$RID-ping" "cslive-$RID-pong" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT
docker network create --label cslive=1 --label "cslive.run=$RID" "$NET" >/dev/null
for r in pong ping; do
  docker run -d --name "cslive-$RID-$r" --label cslive=1 --label "cslive.run=$RID" --network "$NET" \
    -e ROS_DOMAIN_ID=$DOM -e OUT=/out -v "$PWD/smoke":/smoke:ro -v "$PWD/$OUT":/out "$IMG" \
    bash -c "source /opt/ros/jazzy/setup.bash && python3 /smoke/ping.py $r $N > /out/$r.summary.json 2> /out/$r.stderr" >/dev/null
done
docker wait "cslive-$RID-ping" "cslive-$RID-pong"
{
  echo "{\"run\":\"$RID\",\"domain\":$DOM,\"network\":\"$NET\",\"image\":\"$IMG\","
  echo "\"image_id\":\"$(docker image inspect -f '{{.Id}}' $IMG)\","
  echo "\"ping_py_sha256\":\"$(shasum -a 256 smoke/ping.py | cut -d' ' -f1)\"}"
} > "$OUT/manifest.json"
cat "$OUT"/*.summary.json
