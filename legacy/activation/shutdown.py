class Shutdown:
    """Wraps the real ULTRON shutdown coordinator (core.shutdown.graceful_shutdown) -
    stops the wake-word/voice threads and flushes core.state_manager to disk,
    instead of returning a canned success with no effect."""

    def stop(self, runtime=None):
        from core.shutdown import graceful_shutdown

        try:
            graceful_shutdown(runtime)
            return {"success": True, "stopped": True}
        except Exception as e:
            return {"success": False, "stopped": False, "error": str(e)}
