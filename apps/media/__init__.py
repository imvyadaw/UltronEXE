"""Media automations: VLC, Spotify, Windows Media Player, iTunes, YouTube Music."""

from apps.media.vlc import VLCApp
from apps.media.spotify import SpotifyApp
from apps.media.windows_media import WindowsMediaApp
from apps.media.itunes import ITunesApp
from apps.media.youtube_music import YouTubeMusicApp

__all__ = ["VLCApp", "SpotifyApp", "WindowsMediaApp", "ITunesApp", "YouTubeMusicApp"]
