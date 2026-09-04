import requests


class ApiTool:
    def request(self, method, url, **kw):
        kw.setdefault("timeout", 15)
        r = requests.request(method, url, **kw)
        return {"ok": r.ok, "status": r.status_code, "text": r.text[:20000]}
