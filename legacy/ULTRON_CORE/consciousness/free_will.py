class InitiativePolicy:
    def __init__(self, enabled=True):
        self.enabled = enabled

    def can_initiate(self, trigger, risk="LOW"):
        return bool(self.enabled and trigger and risk in ("LOW", "MEDIUM"))
