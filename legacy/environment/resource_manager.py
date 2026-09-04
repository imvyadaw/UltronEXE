from ULTRON_CORE.autonomy.resource_optimizer import ResourceOptimizer


class ResourceManager:
    def snapshot(self):
        return ResourceOptimizer().snapshot()
