"""Publishes the scene-tree pose of each robot and cargo item with the simulation time.

Topics: wcs/observed (JSON, one message per sample), wcs/screenshot (request: {"file": name}).
Poses are read from the Webots nodes, not from the motion controller's state.
"""
import json
import os

import paho.mqtt.client as mqtt
from controller import Supervisor

ROBOTS = os.environ["ROBOTS"].split(",")
CARGO = os.environ["CARGO"].split(",")
SAMPLE_STEPS = int(os.environ.get("WCS_SAMPLE_STEPS", "2"))
OUT = os.environ.get("WCS_OUT", "/out")

sup = Supervisor()
step_ms = int(sup.getBasicTimeStep())
nodes = {r: sup.getFromDef(f"ROBOT_{r}") for r in ROBOTS}
cargo_nodes = {c: sup.getFromDef(f"CARGO_{c}") for c in CARGO}
missing = [k for k, n in {**nodes, **cargo_nodes}.items() if n is None]
if missing:
    raise SystemExit(f"missing nodes: {missing}")

requests = []
client = mqtt.Client(client_id="wcs-observer", protocol=mqtt.MQTTv311)
client.on_connect = lambda c, *_: c.subscribe("wcs/screenshot", qos=1)
client.on_message = lambda _c, _u, m: requests.append(json.loads(m.payload))
client.connect(os.environ["MQTT_BROKER_HOST"], 1883, keepalive=30)
client.loop_start()


def rounded(node):
    return [round(v, 4) for v in node.getPosition()]


n = 0
while sup.step(step_ms) != -1:
    n += 1
    while requests:
        path = os.path.join(OUT, requests.pop(0)["file"])
        sup.exportImage(path, 90)
        client.publish("wcs/screenshot/done", json.dumps({"file": os.path.basename(path), "t_sim": sup.getTime()}), qos=1)
    if n % SAMPLE_STEPS == 0:
        client.publish("wcs/observed", json.dumps({
            "t_sim": round(sup.getTime(), 3),
            "poses": {r: rounded(node) for r, node in nodes.items()},
            "cargo": {c: rounded(node) for c, node in cargo_nodes.items()}}), qos=1)
