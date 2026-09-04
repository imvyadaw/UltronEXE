"""Gaming automations: Steam, Epic Games, Xbox app, Discord (gaming presence)."""

from apps.gaming.steam import SteamApp
from apps.gaming.epic_games import EpicGamesApp
from apps.gaming.xbox import XboxApp
from apps.gaming.discord_gaming import DiscordGamingApp

__all__ = ["SteamApp", "EpicGamesApp", "XboxApp", "DiscordGamingApp"]
