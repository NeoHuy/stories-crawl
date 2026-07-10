# Browser-mode Fallback (FlareSolverr) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Khi chế độ HTTP nhanh bị Cloudflare chặn (kết quả rỗng), tự động tải lại truyện qua một service FlareSolverr chạy container riêng.

**Architecture:** Thêm `FlareSolverrClient` (HTTP client gọi FlareSolverr) và cho `LncrawlAdapter` nhận một `fetcher` để ghi đè khâu tải HTML (`crawler.get_soup`) đi qua FlareSolverr, giữ nguyên parse của lncrawl. `cli.py` điều phối: thử chế độ nhanh, phát hiện bị chặn (mục lục lỗi/0 chương, hoặc mọi chương fail) thì tạo lại adapter với fetcher và tải lại (DB resume). Cờ `--no-browser` tắt fallback.

**Tech Stack:** Python ≥ 3.10, click, requests (đã có qua lncrawl), FlareSolverr container (`ghcr.io/flaresolverr/flaresolverr`).

## Global Constraints

- Không thêm dependency Python mới: dùng `requests` (đã có qua lncrawl) làm HTTP client.
- Endpoint FlareSolverr từ env `STORIES_FLARESOLVERR_URL`, mặc định `http://localhost:8191`.
- API FlareSolverr (đã kiểm chứng): POST `<endpoint>/v1` với `{"cmd":"sessions.create"}` → `{"status":"ok","session":"<uuid>"}`; `{"cmd":"request.get","url":...,"session":<uuid>,"maxTimeout":<ms>}` → `{"status":"ok","solution":{"response":"<html>","status":200}}`; `{"cmd":"sessions.destroy","session":<uuid>}`. Trạng thái lỗi: `status != "ok"`, field `message` chứa mô tả.
- Dấu hiệu trang còn bị chặn trong HTML: chứa `just a moment`, `cf-turnstile`, hoặc `challenge-platform` (so khớp lowercase).
- Cơ chế phát hiện bị chặn ở chế độ nhanh: (a) `get_novel_info` ném lỗi HOẶC trả 0 chương; (b) lượt tải kết thúc với `done == 0` và `failed > 0`.
- Không fallback lặp vô hạn: khi đã ở chế độ browser (fetcher != None) thì không fallback tiếp.
- Tests KHÔNG gọi mạng và KHÔNG chạy FlareSolverr thật — luôn inject/mock.
- `maxTimeout` mặc định 60000 ms.
- Commit message tiếng Anh, quy ước `feat:`/`fix:`/`test:`/`docs:`. Lệnh test: `.venv/bin/pytest`.

**Trạng thái hiện tại của code (đã có, không phá):**
- `stories_crawl/adapters/lncrawl_bridge.py`: `LncrawlAdapter(url)` với `_sources()` (monkeypatch trong test), `get_novel_info`, `get_chapter`, `close`; module cache `_loaded`.
- `stories_crawl/cli.py`: group `main`; `_crawl(lib, lib_dir, url, existing=None)`; lệnh `add`/`update`/`list`/`sources`; `DOWNLOAD_KWARGS` (test tắt sleep); `_library_dir()`.
- `stories_crawl/core/downloader.py`: `download_pending(...) -> DownloadSummary(done, failed, failures)`.
- `tests/conftest.py`: `FakeAdapter` (name="fake", supports fake-site.com) — KHÔNG sửa file này trong plan (giữ ổn định cho test cũ).

---

## File Structure

```
stories_crawl/
├── adapters/
│   ├── flaresolverr.py    # MỚI: FlareSolverrClient, FlareSolverrError
│   └── lncrawl_bridge.py  # SỬA: thêm tham số fetcher, ghi đè get_soup
├── cli.py                 # SỬA: _attempt_crawl + fallback trong _crawl, cờ --no-browser
docker-compose.yml         # MỚI (mẫu)
tests/
├── test_flaresolverr.py   # MỚI
├── test_lncrawl_bridge.py # SỬA: thêm test ghi đè get_soup
└── test_cli.py            # SỬA: thêm test fallback
```

---

### Task 1: `adapters/flaresolverr.py`

**Files:**
- Create: `stories_crawl/adapters/flaresolverr.py`
- Test: `tests/test_flaresolverr.py`

**Interfaces:**
- Consumes: (không có)
- Produces:
  - `class FlareSolverrError(Exception)`
  - `class FlareSolverrClient`:
    - `__init__(self, endpoint: str, *, http=None, max_timeout_ms: int = 60000)` — `http` mặc định module `requests`; lưu `self.session_id = None`.
    - `__enter__(self) -> "FlareSolverrClient"` — gọi `sessions.create`, lưu `session_id`.
    - `__exit__(self, *exc) -> None` — `sessions.destroy` (nuốt `FlareSolverrError`), đặt `session_id=None`.
    - `fetch(self, url: str) -> str` — `request.get` (kèm session nếu có), trả HTML; lỗi mạng/`status!=ok`/HTML còn dấu chặn hoặc rỗng → `FlareSolverrError`.

- [ ] **Step 1: Viết test (sẽ fail)**

`tests/test_flaresolverr.py`:

```python
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
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `.venv/bin/pytest tests/test_flaresolverr.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stories_crawl.adapters.flaresolverr'`

- [ ] **Step 3: Viết `stories_crawl/adapters/flaresolverr.py`**

```python
import requests

_BLOCK_MARKERS = ("just a moment", "cf-turnstile", "challenge-platform")


class FlareSolverrError(Exception):
    pass


class FlareSolverrClient:
    def __init__(self, endpoint, *, http=None, max_timeout_ms: int = 60000):
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
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `.venv/bin/pytest tests/test_flaresolverr.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add stories_crawl/adapters/flaresolverr.py tests/test_flaresolverr.py
git commit -m "feat: FlareSolverr HTTP client for Cloudflare bypass"
```

---

### Task 2: `LncrawlAdapter` nhận `fetcher` để ghi đè `get_soup`

**Files:**
- Modify: `stories_crawl/adapters/lncrawl_bridge.py`
- Test: `tests/test_lncrawl_bridge.py`

**Interfaces:**
- Consumes: `FlareSolverrClient.fetch(url) -> str` (Task 1) — nhưng chỉ cần một đối tượng có `.fetch(url)`.
- Produces: `LncrawlAdapter(url, *, fetcher=None)` — khi `fetcher` khác None, ghi đè `self._crawler.get_soup` để tải HTML qua `fetcher.fetch(url)` rồi `self._crawler.make_soup(html)`.

- [ ] **Step 1: Viết test (sẽ fail)**

Thêm vào `tests/test_lncrawl_bridge.py`. Lớp `FakeCrawler` hiện có cần thêm `make_soup` và `get_soup`; nếu chưa có, bổ sung như dưới (giữ các method cũ `read_novel`/`download_chapter`/`close`):

```python
def test_fetcher_overrides_get_soup(fake_sources):
    from stories_crawl.adapters.lncrawl_bridge import LncrawlAdapter

    class FakeFetcher:
        def __init__(self):
            self.fetched = []

        def fetch(self, url):
            self.fetched.append(url)
            return f"<html><p>{url}</p></html>"

    fetcher = FakeFetcher()
    adapter = LncrawlAdapter("https://supported.com/book/1", fetcher=fetcher)
    soup = adapter._crawler.get_soup("https://supported.com/c/9")
    # đã đi qua fetcher, không chạm scraper
    assert fetcher.fetched == ["https://supported.com/c/9"]
    assert "https://supported.com/c/9" in soup.get_text()
```

Bổ sung cho `FakeCrawler` trong file test (nếu chưa có 2 method này):

```python
    def make_soup(self, html):
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser")

    def get_soup(self, url, *a, **k):
        raise AssertionError("scraper get_soup must not be called in browser mode")
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `.venv/bin/pytest tests/test_lncrawl_bridge.py::test_fetcher_overrides_get_soup -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'fetcher'`

- [ ] **Step 3: Sửa `LncrawlAdapter.__init__`**

Trong `stories_crawl/adapters/lncrawl_bridge.py`, đổi chữ ký và thân `__init__`:

```python
    def __init__(self, url: str, *, fetcher=None):
        super().__init__(url)
        self._crawler = _sources().init_crawler(url)
        self._chapter_map = {}
        if fetcher is not None:
            crawler = self._crawler
            crawler.get_soup = lambda u, *a, **k: crawler.make_soup(fetcher.fetch(u))
```

- [ ] **Step 4: Chạy test, xác nhận pass (kèm test cũ)**

Run: `.venv/bin/pytest tests/test_lncrawl_bridge.py -v`
Expected: tất cả pass (5 cũ + 1 mới)

- [ ] **Step 5: Commit**

```bash
git add stories_crawl/adapters/lncrawl_bridge.py tests/test_lncrawl_bridge.py
git commit -m "feat: route lncrawl fetch through injected fetcher (browser mode)"
```

---

### Task 3: Điều phối fallback trong `cli.py` + cờ `--no-browser`

**Files:**
- Modify: `stories_crawl/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `registry.find_adapter_class` (có sẵn), `download_pending` (có sẵn), `make_slug`/`Library` (có sẵn), `FlareSolverrClient`/`FlareSolverrError` (Task 1), `LncrawlAdapter(url, fetcher=...)` (Task 2 — nhưng bất kỳ adapter nào hỗ trợ kwarg `fetcher`).
- Produces: `_attempt_crawl(lib, lib_dir, url, existing, adapter) -> tuple[bool, object]` (trả `(blocked, row)`); `_crawl(lib, lib_dir, url, existing=None, *, allow_browser=True)`; lệnh `add`/`update` có cờ `--no-browser`.

- [ ] **Step 1: Viết test (sẽ fail)**

Thêm vào `tests/test_cli.py`:

```python
from stories_crawl.adapters.base import BaseAdapter, ChapterRef, NovelInfo


class FakeBlockingAdapter(BaseAdapter):
    """Chế độ nhanh (fetcher=None) trả rỗng; có fetcher thì trả chương thật."""

    name = "fakeblock"

    def __init__(self, url, *, fetcher=None):
        super().__init__(url)
        self.fetcher = fetcher

    @classmethod
    def supports(cls, url):
        return "block-site.com" in url

    def get_novel_info(self, url):
        if self.fetcher is None:
            return NovelInfo(title="", author="", url=url, chapters=[])
        return NovelInfo(
            title="Truyện Chặn", author="TG", url=url,
            chapters=[ChapterRef(1, "Chương 1", url + "/1"),
                      ChapterRef(2, "Chương 2", url + "/2")],
        )

    def get_chapter(self, chapter_url):
        return "nội dung dài " * 50

    def close(self):
        pass


class FakeClientCM:
    """Giả FlareSolverrClient: context manager không cần mạng."""

    last = None

    def __init__(self, endpoint, **kw):
        self.endpoint = endpoint
        FakeClientCM.last = self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def fetch(self, url):
        return "x"


@pytest.fixture
def block_runner(tmp_path, monkeypatch):
    monkeypatch.setenv("STORIES_LIBRARY", str(tmp_path / "library"))
    monkeypatch.setattr(registry, "NATIVE_ADAPTERS", [FakeBlockingAdapter])
    monkeypatch.setattr("stories_crawl.cli.DOWNLOAD_KWARGS", {"sleep": lambda _: None})
    monkeypatch.setattr("stories_crawl.cli.FlareSolverrClient", FakeClientCM)
    return CliRunner(), tmp_path / "library"


def test_add_falls_back_to_flaresolverr(block_runner):
    cli, lib_dir = block_runner
    result = cli.invoke(main, ["add", "https://block-site.com/book/1"])
    assert result.exit_code == 0, result.output
    assert "FlareSolverr" in result.output
    assert "Truyện Chặn" in result.output
    assert "2 OK" in result.output
    assert (lib_dir / "Truyện-Chặn" / "raw" / "0001-Chương-1.md").exists()
    assert FakeClientCM.last is not None  # client đã được mở


def test_no_browser_flag_skips_fallback(block_runner):
    cli, _ = block_runner
    FakeClientCM.last = None
    result = cli.invoke(main, ["add", "--no-browser", "https://block-site.com/book/1"])
    assert result.exit_code != 0
    assert "no-browser" in result.output.lower() or "FlareSolverr" in result.output
    assert FakeClientCM.last is None  # không mở client
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `.venv/bin/pytest tests/test_cli.py::test_add_falls_back_to_flaresolverr -v`
Expected: FAIL (chưa có fallback / `--no-browser`)

- [ ] **Step 3: Viết lại `cli.py`**

Thêm import ở đầu file (sau các import hiện có):

```python
from .adapters.flaresolverr import FlareSolverrClient, FlareSolverrError
```

Thay khối `_crawl` hiện tại bằng `_attempt_crawl` + `_crawl` mới:

```python
def _attempt_crawl(lib, lib_dir, url, existing, adapter):
    """Chạy một lượt tải với adapter đã tạo. Trả (blocked, row)."""
    click.echo(f"Đang lấy mục lục: {url}")
    try:
        info = adapter.get_novel_info(url)
    except Exception as e:
        click.echo(f"  (không lấy được mục lục: {e})")
        return True, None
    if not info.chapters:
        click.echo("  (mục lục rỗng)")
        return True, None
    row = existing or lib.get_novel_by_url(url)
    if row is None:
        slug = make_slug(info.title, lib.existing_slugs())
        lib.create_novel(slug, info.title, info.author, url, adapter.name)
        row = lib.get_novel_by_url(url)
    click.echo(f"{info.title} — {info.author} ({len(info.chapters)} chương)")
    new = lib.add_chapters(row["id"], info.chapters)
    if new:
        click.echo(f"{new} chương mới trong mục lục")
    summary = download_pending(
        adapter, lib, lib_dir, row, log=click.echo, **DOWNLOAD_KWARGS
    )
    click.echo(f"Hoàn tất: {summary.done} OK, {summary.failed} lỗi")
    for idx, title, err in summary.failures:
        click.echo(f"  - chương {idx} ({title}): {err}")
    blocked = summary.done == 0 and summary.failed > 0
    return blocked, row


def _crawl(lib, lib_dir, url, existing=None, *, allow_browser=True):
    try:
        adapter_cls = registry.find_adapter_class(url)
    except UnsupportedSourceError:
        raise click.ClickException(
            f"Nguồn không được hỗ trợ: {url} — xem 'crawl sources'"
        )

    adapter = adapter_cls(url)
    try:
        blocked, _ = _attempt_crawl(lib, lib_dir, url, existing, adapter)
    finally:
        adapter.close()
    if not blocked:
        return

    if not allow_browser:
        raise click.ClickException(
            "Trang có vẻ bị Cloudflare chặn. Bỏ cờ --no-browser để thử qua FlareSolverr."
        )

    click.echo("Trang có vẻ bị chặn — chuyển sang FlareSolverr...")
    endpoint = os.environ.get("STORIES_FLARESOLVERR_URL", "http://localhost:8191")
    try:
        with FlareSolverrClient(endpoint) as client:
            adapter = adapter_cls(url, fetcher=client)
            try:
                blocked2, _ = _attempt_crawl(lib, lib_dir, url, existing, adapter)
            finally:
                adapter.close()
    except FlareSolverrError as e:
        raise click.ClickException(
            f"Không dùng được FlareSolverr ({endpoint}): {e}. "
            f"Kiểm tra container FlareSolverr và biến STORIES_FLARESOLVERR_URL."
        )
    if blocked2:
        raise click.ClickException(
            "Vẫn không tải được qua FlareSolverr — trang có thể chặn mạnh."
        )
```

Cập nhật hai lệnh `add`/`update` để có cờ `--no-browser`:

```python
@main.command()
@click.argument("url")
@click.option("--no-browser", is_flag=True,
              help="Tắt fallback FlareSolverr khi trang bị chặn.")
def add(url, no_browser):
    """Thêm truyện mới vào kho và tải toàn bộ chương."""
    lib_dir = _library_dir()
    lib = Library(lib_dir / "library.db")
    try:
        _crawl(lib, lib_dir, url, allow_browser=not no_browser)
    finally:
        lib.close()


@main.command()
@click.argument("key")
@click.option("--no-browser", is_flag=True,
              help="Tắt fallback FlareSolverr khi trang bị chặn.")
def update(key, no_browser):
    """Tải các chương mới/còn thiếu của truyện đã có (theo slug hoặc id)."""
    lib_dir = _library_dir()
    lib = Library(lib_dir / "library.db")
    try:
        row = lib.get_novel(key)
        if row is None:
            raise click.ClickException(f"Không tìm thấy truyện: {key}")
        _crawl(lib, lib_dir, row["source_url"], existing=row,
               allow_browser=not no_browser)
    finally:
        lib.close()
```

- [ ] **Step 4: Chạy toàn bộ test, xác nhận pass**

Run: `.venv/bin/pytest tests/ -v`
Expected: tất cả pass (bộ cũ 34 + flaresolverr 5 + bridge 1 + cli 2 = 42)

**Bắt buộc sửa test cũ `test_add_metadata_fetch_failure`** (tests/test_cli.py:41-51): trước đây `get_novel_info` ném lỗi → `ClickException "Không lấy được thông tin truyện"`. Hành vi đó đã bỏ — giờ lỗi mục lục = coi như bị chặn → kích hoạt fallback. `FakeAdapter` (conftest) không nhận kwarg `fetcher` và fixture `runner` không mock `FlareSolverrClient`, nên nếu để nguyên, fallback sẽ cố gọi FlareSolverr thật/raise TypeError. Sửa test này chạy với `--no-browser` để có đường lỗi tất định, không mạng:

```python
def test_add_metadata_fetch_failure(runner, monkeypatch):
    cli, _ = runner

    def _boom(self, url):
        raise RuntimeError("mất kết nối")

    monkeypatch.setattr(FakeAdapter, "get_novel_info", _boom)
    result = cli.invoke(main, ["add", "--no-browser", "https://fake-site.com/book/1"])
    assert result.exit_code != 0
    assert "bị Cloudflare chặn" in result.output
    assert "Traceback" not in result.output
```

- [ ] **Step 5: Commit**

```bash
git add stories_crawl/cli.py tests/test_cli.py
git commit -m "feat: auto-fallback to FlareSolverr on blocked sites with --no-browser opt-out"
```

---

### Task 4: docker-compose mẫu, README, smoke test thật

**Files:**
- Create: `docker-compose.yml`
- Modify: `README.md`

**Interfaces:**
- Consumes: toàn bộ tính năng đã xong.
- Produces: tài liệu triển khai + xác nhận chạy thật với FlareSolverr.

- [ ] **Step 1: Tạo `docker-compose.yml`**

```yaml
services:
  app:
    build: .
    environment:
      STORIES_FLARESOLVERR_URL: http://flaresolverr:8191
      STORIES_LIBRARY: /data/library
    volumes:
      - ./library:/data/library
    depends_on:
      - flaresolverr
    # ví dụ: docker compose run --rm app crawl add <url>

  flaresolverr:
    image: ghcr.io/flaresolverr/flaresolverr:latest
    environment:
      LOG_LEVEL: warning
    shm_size: 1g
    ports:
      - "8191:8191"
```

- [ ] **Step 2: Smoke test thật**

Khởi động FlareSolverr rồi thử một truyện trên trang bị chặn:

```bash
docker run -d --name fs -p 8191:8191 --shm-size=1g ghcr.io/flaresolverr/flaresolverr:latest
# chờ ~8s cho service sẵn sàng
STORIES_FLARESOLVERR_URL=http://localhost:8191 \
  .venv/bin/crawl add 'https://www.69shuba.com/book/48146.htm'
```

Kiểm tra:
- Log in ra "Trang có vẻ bị chặn — chuyển sang FlareSolverr..." (chế độ nhanh thất bại, fallback kích hoạt).
- Tải được ít nhất vài chương; mở 1 file `.md` trong `library/<slug>/raw/` thấy văn bản tiếng Trung sạch (không HTML, không "Just a moment").
- Chạy lại lệnh → resume, không tải lại chương đã xong.
- Test `--no-browser`: `crawl add --no-browser <url 69shuba>` → dừng với thông báo gợi ý bỏ cờ, không mở FlareSolverr.

Dọn: `docker rm -f fs`.

Nếu ghi đè `get_soup` không đủ cho 69shuba (nguồn này có logic browser nội bộ riêng), thử một nguồn Cloudflare khác trong `crawl sources` và ghi lại nguồn dùng được vào commit message. Nếu không nguồn nào qua được, đây là kết quả DONE_WITH_CONCERNS — báo chính xác, không giả kết quả.

- [ ] **Step 3: Cập nhật README**

Thêm mục vào `README.md` (sau phần sử dụng), thay phần "Hạn chế đã biết" cũ về Cloudflare bằng nội dung mới:

```markdown
## Vượt Cloudflare (chế độ FlareSolverr)

Một số nguồn (69shuba, ixdzs8, bq99...) chặn bằng Cloudflare/Turnstile. Khi chế
độ tải nhanh cho kết quả rỗng, tool **tự động** thử lại qua một service
[FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) chạy container riêng.

Chạy FlareSolverr rồi trỏ tool tới nó:

    docker run -d --name fs -p 8191:8191 --shm-size=1g \
      ghcr.io/flaresolverr/flaresolverr:latest
    STORIES_FLARESOLVERR_URL=http://localhost:8191 crawl add <url>

Hoặc dùng `docker-compose.yml` mẫu (service `app` + `flaresolverr`).

- Mặc định endpoint là `http://localhost:8191` (đổi bằng `STORIES_FLARESOLVERR_URL`).
- Cờ `--no-browser` tắt fallback: `crawl add --no-browser <url>`.
- FlareSolverr chạy trên Linux/Docker (kể cả server không màn hình). Tỉ lệ vượt
  Turnstile không đảm bảo 100%; chương không lấy được sẽ retry lần `update` sau.
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml README.md
git commit -m "docs: FlareSolverr compose sample and usage guide"
```

---

## Self-review đã thực hiện

- **Spec coverage:** `FlareSolverrClient` + session lifecycle (Task 1); ghi đè `get_soup` qua fetcher (Task 2); điều phối fallback theo cơ chế phát hiện rỗng/thất bại + `--no-browser` + env endpoint (Task 3); docker-compose + README + smoke test thật (Task 4). Cơ chế phát hiện đúng bản spec đã sửa (không dựa CloudflareException).
- **Placeholder scan:** không có TODO/TBD; mọi step code có mã đầy đủ.
- **Type consistency:** `FlareSolverrClient(endpoint, *, http, max_timeout_ms)` + `.fetch(url)->str` nhất quán Task 1→2→3; `LncrawlAdapter(url, *, fetcher=None)` nhất quán Task 2→3; `_attempt_crawl(...) -> (blocked, row)` và `_crawl(..., *, allow_browser)` nhất quán trong Task 3; `DownloadSummary.done/failed` khớp downloader hiện có.
- **Rủi ro còn lại (xử lý ở Task 4 smoke test):** 69shuba có logic browser nội bộ của lncrawl; việc ghi đè `get_soup` có thể tương tác bất ngờ — smoke test xác minh thực tế, có phương án đổi nguồn. Đây là điểm chưa kiểm chứng end-to-end (mới verify từng mắt xích rời).
