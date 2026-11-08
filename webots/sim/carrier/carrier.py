"""Kinematic carrier motion and cargo handling for the experiment world.

Moves each ROBOT_<id> node along a waypoint list at a constant speed in simulation time by
writing its translation and yaw from a supervisor. A lifted CARGO_<id> node follows its holder.
There is no dynamics, sensing or collision handling, and every robot class uses the same motion.

Topics:
  simulator/request   {"action", "robotId", "actionId", ...}
                      move: "path" is "[[x, y], ...]", "speed" in m/s; replaces the current path.
                      cancelMove: stops the robot where it is.
                      liftUp: takes the nearest cargo within PICKUP_RADIUS_M, from the floor or
                      from another robot. liftDown: places the held cargo on the floor.
  simulator/response  {"actionId", "result"}: move answers when the last waypoint is reached.
  robot/<id>/status/position  {"robotId", "x", "y", "theta", "state"} at 5 Hz of simulation time.
"""
import json
import math
import os

import paho.mqtt.client as mqtt
from controller import Supervisor

ROBOTS = os.environ["ROBOTS"].split(",")
CARGO = os.environ["CARGO"].split(",")
STATUS_PERIOD_S = 0.2
PICKUP_RADIUS_M = 1.5
RAISED_Z = 0.55
FLOOR_Z = 0.1


class Carrier:
    def __init__(self, robot_id, node):
        self.id = robot_id
        self.translation = node.getField("translation")
        self.rotation = node.getField("rotation")
        self.x, self.y, self.z = self.translation.getSFVec3f()
        self.theta = 0.0
        self.path, self.speed, self.action_id = [], 0.0, None
        self.state = "IDLE"

    def start(self, action_id, path, speed):
        self.path, self.speed, self.action_id = list(path), speed, action_id
        self.state = "MOVING"

    def cancel(self):
        self.path, self.speed = [], 0.0
        self.state = "IDLE"

    def advance(self, dt):
        """Returns the action id when the last waypoint is reached in this step."""
        budget = self.speed * dt
        while self.path and budget > 0.0:
            tx, ty = self.path[0]
            dx, dy = tx - self.x, ty - self.y
            dist = math.hypot(dx, dy)
            if dist > 0.0:
                self.theta = math.atan2(dy, dx)
            if dist <= budget:
                self.x, self.y = tx, ty
                self.path.pop(0)
                budget -= dist
            else:
                self.x += dx / dist * budget
                self.y += dy / dist * budget
                budget = 0.0
        self.translation.setSFVec3f([self.x, self.y, self.z])
        self.rotation.setSFRotation([0.0, 0.0, 1.0, self.theta])
        if not self.path and self.state == "MOVING":
            self.state = "ARRIVED"
            return self.action_id
        return None


class Cargo:
    def __init__(self, node):
        self.translation = node.getField("translation")
        self.x, self.y, _ = self.translation.getSFVec3f()
        self.holder = None

    def follow(self):
        if self.holder is not None:
            self.x, self.y = self.holder.x, self.holder.y
            self.translation.setSFVec3f([self.x, self.y, RAISED_Z])

    def place(self):
        self.holder = None
        self.translation.setSFVec3f([self.x, self.y, FLOOR_Z])


sup = Supervisor()
step_ms = int(sup.getBasicTimeStep())
carriers = {r: Carrier(r, sup.getFromDef(f"ROBOT_{r}")) for r in ROBOTS}
cargo_items = [Cargo(sup.getFromDef(f"CARGO_{c}")) for c in CARGO]

requests = []
client = mqtt.Client(client_id="wcs-carrier", protocol=mqtt.MQTTv311)
client.on_connect = lambda c, *_: c.subscribe("simulator/request", qos=1)
client.on_message = lambda _c, _u, m: requests.append(json.loads(m.payload))
client.connect(os.environ["MQTT_BROKER_HOST"], 1883, keepalive=30)
client.loop_start()


def respond(action_id, ok):
    client.publish("simulator/response", json.dumps({"actionId": action_id, "result": "success" if ok else "fail"}), qos=1)


def lift_up(carrier):
    near = [c for c in cargo_items if c.holder is not carrier
            and math.hypot(c.x - carrier.x, c.y - carrier.y) <= PICKUP_RADIUS_M]
    if not near:
        return False
    near[0].holder = carrier
    return True


def lift_down(carrier):
    held = [c for c in cargo_items if c.holder is carrier]
    for c in held:
        c.place()
    return bool(held)


def handle(req):
    carrier = carriers.get(req.get("robotId"))
    action = req.get("action")
    if carrier is None:
        respond(req.get("actionId"), False)
    elif action == "move":
        carrier.start(req["actionId"], json.loads(req["path"]), float(req["speed"]))
    elif action == "cancelMove":
        carrier.cancel()
        respond(req.get("actionId"), True)
    elif action == "liftUp":
        respond(req.get("actionId"), lift_up(carrier))
    elif action == "liftDown":
        respond(req.get("actionId"), lift_down(carrier))
    else:
        respond(req.get("actionId"), False)


next_status = 0.0
while sup.step(step_ms) != -1:
    while requests:
        handle(requests.pop(0))
    for carrier in carriers.values():
        done = carrier.advance(step_ms / 1000.0)
        if done is not None:
            respond(done, True)
    for item in cargo_items:
        item.follow()
    if sup.getTime() >= next_status:
        next_status += STATUS_PERIOD_S
        for c in carriers.values():
            client.publish(f"robot/{c.id}/status/position",
                           json.dumps({"robotId": c.id, "x": c.x, "y": c.y, "theta": c.theta, "state": c.state}))
