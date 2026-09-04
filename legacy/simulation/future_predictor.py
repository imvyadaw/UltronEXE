class FuturePredictor:
    def predict(self, history):
        return {
            "sample_size": len(history),
            "success_rate": sum(bool(x.get("success")) for x in history) / max(1, len(history)),
        }
