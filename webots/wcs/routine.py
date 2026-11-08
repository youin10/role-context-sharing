"""Coordination routine shared by every arm.

The routine reads only the view of the agent that currently coordinates. While a request is
pending, facts of the blocking contexts hold it; a RobotLocatedAt fact about the requesting robot
itself does not count. An empty set releases it. With the detour policy a blocked request takes
its alternative path instead of waiting. The routine is fixed and hand-written, not a synthesized
plan.
"""
DISPLAY = {"RobotLocatedAt": "node", "ZoneStatus": "congestion", "RobotStopped": "elapsedSeconds",
           "CargoCarriedBy": "robot"}


class CrossingRoutine:
    def __init__(self, view, issue_move, log):
        self.view, self.issue_move, self.log = view, issue_move, log
        self.pending = {}

    def request(self, task, robot, path, blocks=("RobotLocatedAt",), policy="hold", alt=None):
        self.pending[task] = {"robot": robot, "path": path, "blocks": list(blocks), "policy": policy,
                              "alt": alt, "last": None}
        self.evaluate()

    def occupants(self, req):
        out = {}
        for key, value in self.view().items():
            context, instance = key.split("/", 1)
            if context in req["blocks"] and instance != req["robot"]:
                out[instance] = value[DISPLAY[context]]
        return out

    def evaluate(self):
        for task, req in list(self.pending.items()):
            occupants = self.occupants(req)
            if occupants:
                outcome = "detour" if req["policy"] == "detour" else "hold"
            else:
                outcome = "release"
            if (outcome, occupants) != req["last"]:
                req["last"] = (outcome, occupants)
                self.log("decision", task=task, robot=req["robot"], outcome=outcome, occupants=occupants)
            if outcome != "hold":
                del self.pending[task]
                self.issue_move(task, req["robot"], req["alt"] if outcome == "detour" else req["path"])
