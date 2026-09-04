import os, shutil


class ResourceOptimizer:
    def snapshot(self):
        d = shutil.disk_usage(os.getcwd())
        return {"cpu_count": os.cpu_count(), "disk_free": d.free, "disk_total": d.total}
