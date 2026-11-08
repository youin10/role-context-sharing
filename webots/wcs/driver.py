"""Closed loop of one run: observation -> reports -> sharing -> routine -> simulator commands."""
import json
import math
import queue
import time
import traceback

from wcs.routine import CrossingRoutine
from wcs.sharing import envelope

SPEED = 2.0
ARRIVAL_TOLERANCE = 0.2
QUIET_TOLERANCE = 0.01
MOVED_TOLERANCE = 0.005
RAISED_Z = 0.3
WALL_LIMIT_S = 400.0
ZONE = "apron_zone"
ZONE_CELL = "apron"
ZONE_MONITOR = "cam1"
STOP_OBSERVER = "cam1"


class Driver:
    def __init__(self, run_id, scenario, arm, topology, link, log_path):
        self.run_id, self.sc, self.arm, self.topo, self.link = run_id, scenario, arm, topology, link
        self.reporters = set(scenario["reporters"])
        self.owner = scenario["consumers"][0]
        self.log_file = open(log_path, "w")
        self.seq = 0
        self.t_sim = None
        self.t0 = time.monotonic()
        self.counts = {}
        self.cells, self.congestion, self.holder = {}, None, {}
        self.poses, self.history = {}, {}
        self.moves, self.arrived, self.responded = {}, set(), set()
        self.active = {}
        self.last_motion, self.stop_reported = {}, {}
        self.step_index, self.step_started = 0, None
        self.ready = False
        self.routine = CrossingRoutine(lambda: arm.view(self.owner), self.issue_move, self.log)

    def log(self, rec, **fields):
        self.seq += 1
        row = {"seq": self.seq, "t_sim": self.t_sim, "t_wall": round(time.monotonic() - self.t0, 3), "rec": rec, **fields}
        self.log_file.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        self.log_file.flush()

    # sharing ---------------------------------------------------------------------------
    def flush_calls(self):
        for agent, (kind, context, instance, value) in self.arm.take_calls():
            self.log("notify", agent=agent, kind=kind, context=context, instance=instance, value=value)
        self.log("state", views=self.arm.views(), store=self.arm.store())
        self.routine.evaluate()

    def submit(self, producer, context, instance, value, rec="report", cause=None):
        key = (context, instance)
        self.counts[key] = self.counts.get(key, 0) + 1
        n = self.counts[key]
        env = envelope(self.run_id, producer, context, instance, n, int(self.t_sim * 1000), value)
        self.log(rec, producer=producer, context=context, instance=instance, value=value, n=n, cause=cause)
        rejected = self.arm.report(env)
        if rejected:
            self.log("rejected", items=rejected)
        self.flush_calls()

    # commands --------------------------------------------------------------------------
    def issue_move(self, task, robot, path):
        action_id = f"{self.run_id}:{task}"
        self.moves[task] = {"robot": robot, "target": path[-1], "action_id": action_id}
        self.active[robot] = {"task": task, "t": self.t_sim}
        self.log("command", task=task, robot=robot, path=path, action_id=action_id)
        self.link.move(robot, action_id, path, SPEED)

    def issue_lift(self, action, spec):
        action_id = f"{self.run_id}:{spec['task']}"
        self.log("lift", action=action, task=spec["task"], robot=spec["robot"], action_id=action_id)
        self.link.request(action, spec["robot"], action_id)

    # observations ----------------------------------------------------------------------
    def observe_locations(self):
        for robot, (x, y, _z) in sorted(self.poses.items()):
            cell = self.topo.cell(x, y)
            if cell != self.cells.get(robot):
                self.cells[robot] = cell
                self.submit(robot, "RobotLocatedAt", robot, {"node": cell})

    def observe_zone(self):
        count = sum(1 for c in self.cells.values() if c == ZONE_CELL)
        if count != self.congestion:
            self.congestion = count
            self.submit(ZONE_MONITOR, "ZoneStatus", ZONE, {"congestion": count, "access": "open"})

    def observe_stops(self):
        for robot, (x, y, _z) in sorted(self.poses.items()):
            hist = self.history[robot]
            moved = len(hist) > 1 and math.hypot(x - hist[-2][1], y - hist[-2][2]) > MOVED_TOLERANCE
            if moved:
                self.last_motion[robot] = self.t_sim
                if robot in self.stop_reported:
                    del self.stop_reported[robot]
                    self.submit(STOP_OBSERVER, "RobotStopped", robot, None, cause="motion resumed")
            task = self.active.get(robot)
            if task is None:
                continue
            elapsed = int(self.t_sim - max(self.last_motion.get(robot, task["t"]), task["t"]))
            if elapsed >= 1 and elapsed != self.stop_reported.get(robot):
                self.stop_reported[robot] = elapsed
                self.submit(STOP_OBSERVER, "RobotStopped", robot, {"elapsedSeconds": elapsed})

    def observe_cargo(self, cargo_poses):
        for cargo, (x, y, z) in sorted(cargo_poses.items()):
            current = self.holder.get(cargo)
            if z >= RAISED_Z:
                nearest = min(self.poses, key=lambda r: math.hypot(self.poses[r][0] - x, self.poses[r][1] - y))
                if nearest != current:
                    self.holder[cargo] = nearest
                    self.submit(nearest, "CargoCarriedBy", cargo, {"robot": nearest})
            elif current is not None:
                self.holder[cargo] = None
                self.submit(current, "CargoCarriedBy", cargo, None, cause="cargo placed at destination")

    def on_sample(self, msg):
        self.t_sim = msg["t_sim"]
        self.poses = msg["poses"]
        self.log("sample", poses=msg["poses"], cargo=msg["cargo"])
        for robot, (x, y, _z) in self.poses.items():
            self.history.setdefault(robot, []).append((self.t_sim, x, y))
        if "location" in self.reporters:
            self.observe_locations()
        else:
            self.cells = {r: self.topo.cell(p[0], p[1]) for r, p in self.poses.items()}
        if "zone" in self.reporters:
            self.observe_zone()
        if "stop" in self.reporters:
            self.observe_stops()
        if "cargo" in self.reporters:
            self.observe_cargo(msg["cargo"])
        for task, move in self.moves.items():
            if task in self.responded and task not in self.arrived:
                x, y, _z = self.poses[move["robot"]]
                if math.hypot(x - move["target"][0], y - move["target"][1]) <= ARRIVAL_TOLERANCE:
                    self.arrived.add(task)
                    self.active.pop(move["robot"], None)
                    self.log("arrived", task=task, robot=move["robot"], pose=[x, y])

    def on_response(self, msg):
        for task, move in self.moves.items():
            if move["action_id"] == msg.get("actionId"):
                self.log("response", task=task, result=msg.get("result"))
                if msg.get("result") == "success":
                    self.responded.add(task)
                return
        self.log("response", action_id=msg.get("actionId"), result=msg.get("result"))

    def is_quiet(self, robot, span):
        hist = self.history.get(robot, [])
        if not hist or hist[-1][0] - hist[0][0] < span:
            return False
        _, x, y = hist[-1]
        for t, hx, hy in reversed(hist):
            if self.t_sim - t > span:
                return True
            if math.hypot(hx - x, hy - y) > QUIET_TOLERANCE:
                return False
        return False

    # scenario steps --------------------------------------------------------------------
    def wait_done(self, w):
        if "cell" in w:
            robot, cell = w["cell"]
            return self.cells.get(robot) == cell
        if "arrived" in w:
            return w["arrived"] in self.arrived
        if "dwell" in w:
            return self.t_sim - self.step_started >= w["dwell"]
        if "stopped" in w:
            robot, seconds = w["stopped"]
            return self.stop_reported.get(robot, 0) >= seconds
        if "holder" in w:
            cargo, robot = w["holder"]
            return self.holder.get(cargo) == robot and cargo in self.holder
        if "quiet" in w:
            robots, span = w["quiet"]
            done = all(self.is_quiet(r, span) for r in robots)
            if done:
                self.log("quiet", robots=robots, span_s=span,
                         reason="robots stationary, location reports are sent only on a cell change")
            return done
        raise ValueError(w)

    def run_step(self, step):
        if "move" in step:
            m = step["move"]
            self.issue_move(m["task"], m["robot"], m["path"])
        elif "cancel" in step:
            self.log("cancel", robot=step["cancel"])
            self.link.request("cancelMove", step["cancel"], f"{self.run_id}:cancel:{step['id']}")
        elif "lift" in step:
            self.issue_lift("liftUp", step["lift"])
        elif "lower" in step:
            self.issue_lift("liftDown", step["lower"])
        elif "request" in step:
            r = step["request"]
            self.log("request", task=r["task"], robot=r["robot"])
            self.routine.request(r["task"], r["robot"], r["path"], r.get("blocks", ["RobotLocatedAt"]),
                                 r.get("policy", "hold"), r.get("alt"))
        elif "change" in step:
            ch = step["change"]
            self.log("change", id=ch["id"], phase="begin")
            meta = self.arm.change(ch, self.t_sim)
            self.log("change", id=ch["id"], phase="applied", meta=meta)
            if "owner" in ch and not (meta or {}).get("skipped"):
                self.owner = ch["owner"]
                self.log("owner", agent=self.owner)
            self.flush_calls()
        elif "invalid_change" in step:
            ch = step["invalid_change"]
            if self.arm.name in ch.get("arms", [self.arm.name]):
                self.log("refused", id=ch["id"], code=self.arm.validate_revision(ch))
                self.flush_calls()
        elif "inject" in step:
            i = step["inject"]
            self.submit(i["producer"], i.get("context", "RobotLocatedAt"), i["instance"], i["value"], rec="inject")
        elif "checkpoint" in step:
            self.log("checkpoint", name=step["checkpoint"], views=self.arm.views(), store=self.arm.store())
        elif "shot" in step:
            name = f"{step['shot']}.jpg"
            self.log("shot", file=name)
            self.link.screenshot(name)

    def advance(self):
        steps = self.sc["steps"]
        while self.step_index < len(steps):
            step = steps[self.step_index]
            if self.step_started is None:
                self.step_started = self.t_sim
                self.log("step", id=step["id"], body={k: v for k, v in step.items() if k != "id"})
            if "wait" in step:
                if not self.wait_done(step["wait"]):
                    return
            else:
                self.run_step(step)
            self.step_index += 1
            self.step_started = None

    def loop(self):
        limit = self.sc["limit_sim_s"]
        t_first = None
        while self.step_index < len(self.sc["steps"]):
            if time.monotonic() - self.t0 > WALL_LIMIT_S:
                return "wall-timeout"
            try:
                topic, msg = self.link.inbox.get(timeout=1.0)
            except queue.Empty:
                continue
            if topic.startswith("robot/"):
                self.ready = True
            elif topic == "simulator/response":
                self.on_response(msg)
            elif topic == "wcs/screenshot/done":
                self.log("shot-done", **msg)
            elif topic == "wcs/observed":
                self.on_sample(msg)
                t_first = t_first if t_first is not None else self.t_sim
                if self.ready:
                    self.advance()
                if self.t_sim - t_first > limit:
                    return "sim-timeout"
        return "ok"

    def run(self):
        self.log("start", run=self.run_id, scenario=self.sc["id"], arm=self.arm.name, fault=self.arm.fault,
                 setup=self.arm.setup)
        try:
            status = self.loop()
        except Exception:
            status = "error"
            self.log("error", trace=traceback.format_exc())
        self.log("end", status=status, views=self.arm.views(), store=self.arm.store(), step=self.step_index,
                 outside_report_cfg=self.arm.outside())
        self.log_file.close()
        return status
