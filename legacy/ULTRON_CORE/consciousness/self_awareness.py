import platform, sys, time


class SelfAwareness:
    def __init__(self):
        self.mode = "ready"
        self.goal = ""
        self.last_error = ""

    def snapshot(self):
        return {
            "mode": self.mode,
            "goal": self.goal,
            "last_error": self.last_error,
            "runtime": {"python": sys.version.split()[0], "platform": platform.platform(), "time": time.time()},
        }

    def set_goal(self, g):
        self.goal = g
        self.mode = "planning"
