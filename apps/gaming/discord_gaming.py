"""
Discord gaming-presence helpers
==================================
Complements apps/communication/discord.py with the gaming-specific bits:
detecting which known games are currently running (for Rich Presence
context) - actually setting a custom Rich Presence status requires a
running game to register with Discord's local IPC, which is out of
scope for simple app automation, so this focuses on detection + jumping
into voice/game-focused channels.
"""

from typing import Dict, List

from apps.base_app import BaseApp
from apps.communication.discord import DiscordApp

try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

KNOWN_GAME_PROCESSES = [
    "steam.exe",
    "epicgameslauncher.exe",
    "riotclientservices.exe",
    "valorant.exe",
    "csgo.exe",
    "cs2.exe",
    "leagueclient.exe",
    "fortniteclient-win64-shipping.exe",
    "minecraft.exe",
    "javaw.exe",
]


class DiscordGamingApp(BaseApp):
    """Detect running games and jump into voice/gaming channels on Discord."""

    APP_NAME = "discord"
    PROCESS_NAMES = ["discord.exe", "discord"]
    EXE_HINTS = ["discord", "discord.exe"]

    def __init__(self):
        super().__init__()
        self._discord = DiscordApp()

    def detect_running_games(self) -> Dict:
        if not HAS_PSUTIL:
            return {"error": "psutil not installed - run: pip install psutil"}
        try:
            running: List[str] = []
            for p in psutil.process_iter(["name"]):
                name = (p.info.get("name") or "").lower()
                if name in KNOWN_GAME_PROCESSES:
                    running.append(name)
            return {"success": True, "running_games": running}
        except Exception as e:
            return {"error": str(e)}

    def join_voice_channel(self, server_id: str, channel_id: str) -> Dict:
        return self._discord.open_channel(server_id, channel_id)

    def open_and_detect(self) -> Dict:
        opened = self.open()
        games = self.detect_running_games()
        return {"discord": opened, "games": games}
