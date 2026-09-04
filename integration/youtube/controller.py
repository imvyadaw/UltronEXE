"""
YouTube integration
====================
YouTube Data API v3 wrapper: search, video/channel details, playlist
management, comments. This is distinct from browser/chrome/chrome.py's
youtube_search/youtube_control, which drive the *actual open browser tab*
(play/pause/skip in whatever video is already on screen) - use this module
instead when you need structured data (titles, view counts, playlists) or
to manage the user's own channel/playlists via OAuth.

Setup (.env): YOUTUBE_API_KEY (Google Cloud Console -> enable "YouTube
Data API v3" -> create an API key) covers search/read-only calls. Actions
on the user's own account (add to playlist, etc.) additionally need OAuth
- reuses skills/email/gmail.py's Google OAuth client if you add the
https://www.googleapis.com/auth/youtube scope to it.
"""

import os
from typing import Dict, Optional

import requests

API_URL = "https://www.googleapis.com/youtube/v3"


class YouTubeClient:
    """Read-oriented wrapper around the YouTube Data API v3 (API-key auth)."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("YOUTUBE_API_KEY")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _check(self) -> Optional[Dict]:
        if not self.is_configured():
            return {"success": False, "error": "YOUTUBE_API_KEY not set in .env"}
        return None

    def search_videos(self, query: str, max_results: int = 5) -> Dict:
        err = self._check()
        if err:
            return err
        try:
            resp = requests.get(
                f"{API_URL}/search",
                params={
                    "part": "snippet",
                    "q": query,
                    "type": "video",
                    "maxResults": max_results,
                    "key": self.api_key,
                },
                timeout=15,
            )
            resp.raise_for_status()
            videos = [
                {
                    "video_id": v["id"]["videoId"],
                    "title": v["snippet"]["title"],
                    "channel": v["snippet"]["channelTitle"],
                    "published_at": v["snippet"]["publishedAt"],
                    "url": f"https://www.youtube.com/watch?v={v['id']['videoId']}",
                }
                for v in resp.json().get("items", [])
            ]
            return {"success": True, "count": len(videos), "videos": videos}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_video_details(self, video_id: str) -> Dict:
        err = self._check()
        if err:
            return err
        try:
            resp = requests.get(
                f"{API_URL}/videos",
                params={
                    "part": "snippet,statistics,contentDetails",
                    "id": video_id,
                    "key": self.api_key,
                },
                timeout=15,
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            if not items:
                return {"success": False, "error": f"Video not found: {video_id}"}
            v = items[0]
            return {
                "success": True,
                "video_id": video_id,
                "title": v["snippet"]["title"],
                "channel": v["snippet"]["channelTitle"],
                "description": v["snippet"]["description"][:500],
                "views": v["statistics"].get("viewCount"),
                "likes": v["statistics"].get("likeCount"),
                "comments": v["statistics"].get("commentCount"),
                "duration": v["contentDetails"]["duration"],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_channel_details(self, channel_id: Optional[str] = None, handle: Optional[str] = None) -> Dict:
        err = self._check()
        if err:
            return err
        try:
            params = {"part": "snippet,statistics", "key": self.api_key}
            if handle:
                params["forHandle"] = handle.lstrip("@")
            elif channel_id:
                params["id"] = channel_id
            else:
                return {"success": False, "error": "Provide either channel_id or handle"}

            resp = requests.get(f"{API_URL}/channels", params=params, timeout=15)
            resp.raise_for_status()
            items = resp.json().get("items", [])
            if not items:
                return {"success": False, "error": "Channel not found"}
            c = items[0]
            return {
                "success": True,
                "channel_id": c["id"],
                "title": c["snippet"]["title"],
                "subscribers": c["statistics"].get("subscriberCount"),
                "total_views": c["statistics"].get("viewCount"),
                "video_count": c["statistics"].get("videoCount"),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_playlist_items(self, playlist_id: str, max_results: int = 20) -> Dict:
        err = self._check()
        if err:
            return err
        try:
            resp = requests.get(
                f"{API_URL}/playlistItems",
                params={
                    "part": "snippet",
                    "playlistId": playlist_id,
                    "maxResults": max_results,
                    "key": self.api_key,
                },
                timeout=15,
            )
            resp.raise_for_status()
            items = [
                {
                    "title": i["snippet"]["title"],
                    "video_id": i["snippet"]["resourceId"]["videoId"],
                    "position": i["snippet"]["position"],
                }
                for i in resp.json().get("items", [])
            ]
            return {"success": True, "count": len(items), "items": items}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_video_comments(self, video_id: str, max_results: int = 10) -> Dict:
        err = self._check()
        if err:
            return err
        try:
            resp = requests.get(
                f"{API_URL}/commentThreads",
                params={
                    "part": "snippet",
                    "videoId": video_id,
                    "maxResults": max_results,
                    "order": "relevance",
                    "key": self.api_key,
                },
                timeout=15,
            )
            resp.raise_for_status()
            comments = [
                {
                    "author": c["snippet"]["topLevelComment"]["snippet"]["authorDisplayName"],
                    "text": c["snippet"]["topLevelComment"]["snippet"]["textDisplay"],
                    "likes": c["snippet"]["topLevelComment"]["snippet"]["likeCount"],
                }
                for c in resp.json().get("items", [])
            ]
            return {"success": True, "count": len(comments), "comments": comments}
        except Exception as e:
            return {"success": False, "error": str(e)}
