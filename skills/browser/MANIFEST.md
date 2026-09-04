# Browser skills

| Tool | Module |
|---|---|
| open_url, open_urls, list_chrome_tabs, close_chrome_tab(s), scroll_chrome, chrome_navigate, type_in_chrome, chrome_keypress, chrome_zoom, youtube_search, youtube_control | browser/chrome/chrome.py |
| list_edge_tabs, close_edge_tab, scroll_edge, edge_navigate, type_in_edge | browser/edge/edge.py |
| list_firefox_tabs, close_firefox_tab, scroll_firefox, firefox_navigate | browser/firefox/firefox.py |
| list_downloads, open_download, get_download_history | browser/downloads/downloads.py |
| (cookie read - module only, not an AI tool by default) | browser/cookies/cookies.py |
| (browser-agnostic scroll/navigate/type/zoom/tabs, auto-detects active browser - module + agents/browser_agent.py only) | browser/automation/automation.py |

All five browser modules are implemented. Edge/Firefox tab automation needs
pywinauto's UI Automation backend (same as Chrome); Firefox additionally needs
its accessibility support enabled (about:config -> accessibility.force_disabled = 0,
on by default in modern Firefox).
