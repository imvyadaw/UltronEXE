# Integrations

Third-party service integrations, separate from skills/ (which covers
first-party OS/file/web/communication capabilities). Each is a standalone
client class with the same `{"success": bool, ...}` return convention used
throughout the rest of Ultron. integration/base_integration.py has shared
helpers (env lookup, a requests wrapper, a token-cache helper) that new
clients can subclass - existing ones predate it and work fine without it.

| Service | Module | Class |
|---|---|---|
| Slack | integration/slack/client.py | `SlackClient` |
| Discord | integration/discord/bot.py | `DiscordClient` |
| Microsoft Teams | integration/teams/connector.py | `TeamsClient` |
| Notion | integration/notion/api.py | `NotionClient` |
| Obsidian | integration/obsidian/vault.py | `ObsidianClient` |
| Spotify | integration/spotify/player.py | `SpotifyClient` |
| YouTube (Data API) | integration/youtube/controller.py | `YouTubeClient` |
| Twitter/X | integration/twitter/poster.py | `TwitterPoster` |
| LinkedIn | integration/linkedin/network.py | `LinkedInNetwork` |
| Gmail | integration/gmail/mailbox.py | `Mailbox` |

All credentials are read from `.env` - see `.env.template` at the repo root
for every variable each client expects. Every client exposes `is_configured()`
(or `is_webhook_configured()`/`is_graph_configured()` for Teams,
`is_read_configured()` alongside `is_configured()` for Twitter, since posting
and reading use different credentials there) so callers can check readiness
before attempting a call and give the user a clear "not set up yet" message
instead of a raw exception.

YouTube here is the **Data API** (search, video/channel stats, playlists,
comments) - not to be confused with `youtube_search`/`youtube_control` in
`ai/tool_runtime.py`, which drive the browser tab that's already open via
`browser/chrome/chrome.py`.

Gmail here (`integration/gmail/mailbox.py`) is a thin subclass of
`skills/email/gmail.py`'s `GmailClient` - same OAuth2 flow and cached
token, no separate setup - kept as its own integration/ module so it sits
alongside the other Phase 11 clients with a couple of mailbox-shaped
convenience methods (`unread_count`, `latest`) on top.

All of the above are AI-callable (`slack_*`, `discord_*`, `teams_*`,
`notion_*`, `obsidian_*`, `spotify_*`, `youtube_data_*`, `twitter_*`,
`linkedin_*`, `mailbox_*` tools) - see ai/new_skills_tools.py for the exact
tool names/args.
