"""MQTT link to the simulator. Callbacks only enqueue; the runner stays single-threaded."""
import json
import queue

import paho.mqtt.client as mqtt


class Link:
    def __init__(self, port, client_id):
        self.inbox = queue.Queue()
        self.client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)
        self.client.on_connect = self._connected
        self.client.on_message = lambda _c, _u, m: self.inbox.put((m.topic, json.loads(m.payload)))
        self.client.connect("127.0.0.1", port, keepalive=30)
        self.client.loop_start()

    @staticmethod
    def _connected(client, *_):
        client.subscribe([("wcs/observed", 1), ("simulator/response", 1), ("wcs/screenshot/done", 1),
                          ("robot/+/status/position", 0)])

    def request(self, action, robot, action_id, **fields):
        self.client.publish("simulator/request", json.dumps(
            {"action": action, "robotId": robot, "actionId": action_id, **fields}), qos=1)

    def move(self, robot, action_id, path, speed):
        self.request("move", robot, action_id, path=json.dumps(path), speed=speed)

    def screenshot(self, name):
        self.client.publish("wcs/screenshot", json.dumps({"file": name}), qos=1)

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()
