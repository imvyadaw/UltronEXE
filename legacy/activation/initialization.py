from .health_check import HealthCheck


class Initialization:
    def run(self):
        return HealthCheck().run()
