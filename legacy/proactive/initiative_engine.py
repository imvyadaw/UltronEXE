from ULTRON_CORE.consciousness.free_will import InitiativePolicy


class InitiativeEngine:
    def __init__(self):
        self.policy = InitiativePolicy()

    def propose(self, trigger, risk="LOW"):
        return {"allowed": self.policy.can_initiate(trigger, risk), "risk": risk}
