import pytest

from stories_crawl.adapters.flaresolverr import FlareSolverrClient, FlareSolverrError


class FakeResp:
    def __init__(self, payload, ok=True):
        self._payload = payload
        self._ok = ok

    def json(self):
        if self._payload is _BAD_JSON:
            raise ValueError("not json")
        return self._payload


_BAD_JSON = object()


class FakeHttp:
    """Ghi lại các lần POST và trả response theo hàng đợi định sẵn."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append(json)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResp(item)


def _ok_session(sid="sid-1"):
    return {"status": "ok", "session": sid}


def _ok_html(html):
    return {"status": "ok", "solution": {"response": html, "status": 200}}


def test_session_lifecycle_and_fetch():
    html = "<html><body>" + "内容" * 100 + "</body></html>"
    http = FakeHttp([_ok_session("abc"), _ok_html(html), {"status": "ok"}])
    with FlareSolverrClient("http://fs:8191", http=http) as c:
        assert c.session_id == "abc"
        out = c.fetch("https://x.com/1")
        assert "内容" in out
    # 3 lệnh: create, request.get (kèm session), destroy
    cmds = [call["cmd"] for call in http.calls]
    assert cmds == ["sessions.create", "request.get", "sessions.destroy"]
    assert http.calls[1]["session"] == "abc"
    assert http.calls[1]["url"] == "https://x.com/1"


def test_fetch_raises_on_blocked_html():
    http = FakeHttp([_ok_session(), _ok_html("<title>Just a moment...</title>")])
    with FlareSolverrClient("http://fs:8191", http=http) as c:
        with pytest.raises(FlareSolverrError):
            c.fetch("https://x.com/1")


def test_fetch_raises_on_status_error():
    http = FakeHttp([_ok_session(), {"status": "error", "message": "boom"}])
    with FlareSolverrClient("http://fs:8191", http=http) as c:
        with pytest.raises(FlareSolverrError):
            c.fetch("https://x.com/1")


def test_network_error_becomes_flaresolverr_error():
    http = FakeHttp([ConnectionError("refused")])
    with pytest.raises(FlareSolverrError):
        FlareSolverrClient("http://fs:8191", http=http).__enter__()


def test_destroy_swallows_errors():
    http = FakeHttp([_ok_session(), ConnectionError("down")])
    c = FlareSolverrClient("http://fs:8191", http=http)
    c.__enter__()
    c.__exit__(None, None, None)  # không raise dù destroy lỗi
    assert c.session_id is None
