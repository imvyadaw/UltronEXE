class DeviceManager:
    """Wraps the real device registry (intelligence.world_state.device_state) -
    returns whatever devices have actually been registered/reported connected,
    instead of an always-empty list."""

    def list(self):
        from intelligence.world_state.device_state import get_device_state

        try:
            devices = get_device_state().connected_devices()
            return {"devices": devices, "authorized_only": True}
        except Exception as e:
            return {"devices": [], "authorized_only": True, "error": str(e)}
