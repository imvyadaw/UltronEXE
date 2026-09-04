import os, platform


class EnvironmentSensor:
    def snapshot(self):
        return {"platform": platform.platform(), "cwd": os.getcwd()}
