class PermissionEngine:
    def check(self, action, risk="LOW"):
        return risk == "LOW"
