import platform


class SystemController:
    def status(self):
        return {"available": True, "platform": platform.platform()}
