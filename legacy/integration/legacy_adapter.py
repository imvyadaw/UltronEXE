class LegacyAdapter:
    def expose(self, obj, names):
        return {n: getattr(obj, n) for n in names if hasattr(obj, n)}
