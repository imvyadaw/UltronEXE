from security.audit import AuditLog


class AuditLogger:
    def __init__(self):
        self.log = AuditLog()

    def record(self, *a, **kw):
        return self.log.record(*a, **kw)
