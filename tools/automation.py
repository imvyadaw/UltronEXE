class AutomationTool:
    def schedule(self, callback, *args, **kwargs):
        if not callback:
            return {"success": False, "error": "no scheduler configured"}
        return callback(*args, **kwargs)
