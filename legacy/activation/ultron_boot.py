from .initialization import Initialization
from security.kill_switch import KillSwitch


class UltronBoot:
    def start(self):
        if KillSwitch().active():
            return {"healthy": False, "error": "kill switch active"}
        return Initialization().run()
