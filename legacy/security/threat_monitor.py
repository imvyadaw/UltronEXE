class ThreatMonitor:
    def inspect(self, event):
        return {
            "suspicious": any(
                x in str(event).lower() for x in ("bypass permission", "credential theft", "disable security")
            )
        }
