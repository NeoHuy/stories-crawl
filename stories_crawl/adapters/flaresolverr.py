import requests

_BLOCK_MARKERS = ("just a moment", "cf-turnstile", "challenge-platform")


class FlareSolverrError(Exception):
    pass


class FlareSolverrClient:
    def __init__(self, endpoint: str, *, http=None, max_timeout_ms: int = 60000):
        self.endpoint = endpoint.rstrip("/") + "/v1"
        self.http = http or requests
        self.max_timeout_ms = max_timeout_ms
        self.session_id = None

    def _post(self, payload):
        try:
            resp = self.http.post(
                self.endpoint, json=payload, timeout=self.max_timeout_ms / 1000 + 30
            )
        except Exception as e:
            raise FlareSolverrError(f"Không gọi được FlareSolverr: {e}")
        try:
            data = resp.json()
        except Exception as e:
            raise FlareSolverrError(f"FlareSolverr trả về không phải JSON: {e}")
        if data.get("status") != "ok":
            raise FlareSolverrError(f"FlareSolverr lỗi: {data.get('message')}")
        return data

    def __enter__(self):
        data = self._post({"cmd": "sessions.create"})
        self.session_id = data.get("session")
        return self

    def __exit__(self, *exc):
        if self.session_id:
            try:
                self._post({"cmd": "sessions.destroy", "session": self.session_id})
            except FlareSolverrError:
                pass
            self.session_id = None

    def fetch(self, url: str) -> str:
        payload = {"cmd": "request.get", "url": url, "maxTimeout": self.max_timeout_ms}
        if self.session_id:
            payload["session"] = self.session_id
        data = self._post(payload)
        html = (data.get("solution") or {}).get("response") or ""
        low = html.lower()
        if len(html) < 100 or any(m in low for m in _BLOCK_MARKERS):
            raise FlareSolverrError(f"FlareSolverr không vượt được challenge: {url}")
        return html
