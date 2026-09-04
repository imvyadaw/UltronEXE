class AccessController:
    def __init__(self):
        self.grants = {}

    def grant(self, p, c):
        self.grants.setdefault(p, set()).add(c)

    def allowed(self, p, c):
        return c in self.grants.get(p, set())
