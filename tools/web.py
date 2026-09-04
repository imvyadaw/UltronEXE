import requests


class WebTool:
    def fetch(self, url, timeout=15):
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "ULTRON-ULTRON/1.0"})
        return {"ok": r.ok, "status": r.status_code, "url": r.url, "text": r.text[:50000]}
