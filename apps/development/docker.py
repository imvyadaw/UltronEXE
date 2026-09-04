"""
Docker automation
====================
CLI-driven (via the `docker` command) rather than GUI automation of
Docker Desktop - far more reliable for container management.
"""

from typing import Dict, List, Optional

from apps.base_app import BaseApp


class DockerApp(BaseApp):
    """List/start/stop containers and images via the Docker CLI."""

    APP_NAME = "docker desktop"
    PROCESS_NAMES = ["docker desktop.exe", "com.docker.backend.exe", "docker"]
    EXE_HINTS = ["docker", "docker.exe"]

    def list_containers(self, all_containers: bool = True) -> Dict:
        args = ["docker", "ps", "--format", "{{.ID}}\t{{.Image}}\t{{.Status}}\t{{.Names}}"]
        if all_containers:
            args.insert(2, "-a")
        result = self.run_and_capture(args)
        if result.get("success"):
            containers = []
            for line in result["stdout"].splitlines():
                parts = line.split("\t")
                if len(parts) == 4:
                    containers.append({"id": parts[0], "image": parts[1], "status": parts[2], "name": parts[3]})
            result["containers"] = containers
        return result

    def list_images(self) -> Dict:
        result = self.run_and_capture(["docker", "images", "--format", "{{.Repository}}\t{{.Tag}}\t{{.Size}}"])
        if result.get("success"):
            images = []
            for line in result["stdout"].splitlines():
                parts = line.split("\t")
                if len(parts) == 3:
                    images.append({"repository": parts[0], "tag": parts[1], "size": parts[2]})
            result["images"] = images
        return result

    def start_container(self, name_or_id: str) -> Dict:
        return self.run_and_capture(["docker", "start", name_or_id])

    def stop_container(self, name_or_id: str) -> Dict:
        return self.run_and_capture(["docker", "stop", name_or_id])

    def remove_container(self, name_or_id: str, force: bool = False) -> Dict:
        args = ["docker", "rm", name_or_id]
        if force:
            args.insert(2, "-f")
        return self.run_and_capture(args)

    def run_container(self, image: str, args: Optional[List[str]] = None, detached: bool = True) -> Dict:
        cmd = ["docker", "run"]
        if detached:
            cmd.append("-d")
        cmd.append(image)
        if args:
            cmd.extend(args)
        return self.run_and_capture(cmd)

    def logs(self, name_or_id: str, tail: int = 100) -> Dict:
        return self.run_and_capture(["docker", "logs", "--tail", str(tail), name_or_id])
