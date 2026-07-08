# stories-crawl Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CLI Python thu thập truyện tiếng Trung về kho cá nhân (markdown + SQLite), dùng lightnovel-crawler làm engine adapter.

**Architecture:** Package `stories_crawl` gồm 4 tầng: `adapters/` (interface + bridge sang lightnovel-crawler), `core/` (registry chọn adapter theo URL, vòng lặp tải có retry/resume), `storage/` (SQLite cho metadata/trạng thái, file markdown cho nội dung), `cli.py` (click). Trạng thái từng chương nằm trong DB nên chạy lại lệnh là resume.

**Tech Stack:** Python ≥ 3.10, click, lightnovel-crawler ≥ 4.10, beautifulsoup4, sqlite3 (stdlib), pytest.

## Global Constraints

- Python ≥ 3.10. Dependencies runtime: `click>=8.1`, `lightnovel-crawler>=4.10`, `beautifulsoup4>=4.12`. Dev: `pytest>=8`.
- Kho mặc định `./library`, override bằng biến môi trường `STORIES_LIBRARY`.
- File nội dung: `library/<slug>/raw/NNNN-<tiêu đề>.md`, UTF-8, dòng đầu `# <tiêu đề chương>`.
- Delay giữa các chương: ngẫu nhiên 1.0–2.0 giây. Retry tối đa 3 lần/chương, backoff 1s rồi 2s.
- Nội dung < 200 ký tự → coi là lỗi (bị chặn), đánh dấu `failed`, không ghi file.
- Test KHÔNG gọi mạng. API lncrawl chỉ được chạm qua `lncrawl_bridge`, trong test luôn monkeypatch.
- Lệnh console script tên `crawl`.
- Commit message tiếng Anh, quy ước `feat:`/`test:`/`docs:`.

**Ghi chú API lightnovel-crawler v4 (đã xác minh bằng cách cài thật):**
- `from lncrawl.context import ctx` → `ctx.sources.load(sync_remote=True)` (chạy thread nền, lần đầu tải index nguồn từ GitHub) → `ctx.sources.ensure_load()` (join thread) → `ctx.sources.init_crawler(url)` trả về instance `Crawler` sẵn dùng, `ctx.sources.find_crawler(url)` trả class hoặc raise nếu không hỗ trợ.
- `from lncrawl.core import Novel, Chapter`; `crawler.read_novel(novel)` điền `novel.title/author/chapters`; mỗi chapter có `.id/.url/.title`; `crawler.download_chapter(chapter)` điền `chapter.body` (HTML).
- `ctx.sources.list()` trả list SourceItem có `.domain`, `.file_path` (dạng `sources/zh/xxx.py`), `.is_disabled`. Trường `.language` thường rỗng — lọc tiếng Trung bằng tiền tố `file_path`.

---

## File Structure

```
pyproject.toml
stories_crawl/
├── __init__.py
├── cli.py                     # click group: add, update, list, sources
├── core/
│   ├── __init__.py
│   ├── registry.py            # find_adapter_class(url)
│   └── downloader.py          # download_pending(...) — vòng lặp tải
├── adapters/
│   ├── __init__.py
│   ├── base.py                # BaseAdapter, NovelInfo, ChapterRef, UnsupportedSourceError
│   ├── lncrawl_bridge.py      # LncrawlAdapter, list_supported_domains
│   └── native/
│       └── __init__.py        # trống — chỗ cho adapter tự viết sau này
└── storage/
    ├── __init__.py
    ├── db.py                  # class Library (SQLite)
    └── files.py               # sanitize, make_slug, chapter_filename, write_chapter
tests/
├── conftest.py                # FakeAdapter dùng chung (tạo ở Task 5)
├── test_db.py
├── test_files.py
├── test_registry.py
├── test_lncrawl_bridge.py
├── test_downloader.py
└── test_cli.py
```

---

### Task 1: Scaffolding + storage/db.py

**Files:**
- Create: `pyproject.toml`, `stories_crawl/__init__.py`, `stories_crawl/storage/__init__.py`, `stories_crawl/storage/db.py`, `.gitignore`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: (không có — task đầu)
- Produces: `class Library` trong `stories_crawl/storage/db.py`:
  - `Library(db_path: str | Path)` — mở/khởi tạo DB, tự tạo thư mục cha
  - `close() -> None`
  - `create_novel(slug: str, title: str, author: str, source_url: str, adapter: str) -> int` — trả về novel id
  - `get_novel_by_url(url: str) -> sqlite3.Row | None`
  - `get_novel(key: str) -> sqlite3.Row | None` — key là id (chuỗi số) hoặc slug
  - `existing_slugs() -> set[str]`
  - `add_chapters(novel_id: int, chapters) -> int` — chapters là iterable có `.idx/.title/.url`; bỏ qua (novel_id, idx) đã tồn tại; trả về số dòng chèn mới
  - `pending_chapters(novel_id: int) -> list[sqlite3.Row]` — status `pending`/`failed`, sắp theo idx
  - `mark_chapter_done(chapter_id: int, file_path: str) -> None`
  - `mark_chapter_failed(chapter_id: int, error: str) -> None`
  - `touch_novel(novel_id: int) -> None` — cập nhật updated_at
  - `list_novels() -> list[sqlite3.Row]` — mỗi row có thêm `total_count`, `done_count`

- [ ] **Step 1: Tạo scaffolding**

`pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "stories-crawl"
version = "0.1.0"
description = "Thu thập truyện về kho cá nhân"
requires-python = ">=3.10"
dependencies = [
    "click>=8.1",
    "lightnovel-crawler>=4.10",
    "beautifulsoup4>=4.12",
]

[project.scripts]
crawl = "stories_crawl.cli:main"

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.setuptools.packages.find]
include = ["stories_crawl*"]
```

`.gitignore`:

```
__pycache__/
*.egg-info/
.venv/
library/
```

`stories_crawl/__init__.py` và `stories_crawl/storage/__init__.py`: file trống.

Tạo venv và cài đặt:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

Lưu ý: bước cài sẽ kéo theo lightnovel-crawler (nhiều dependency, mất vài phút).

- [ ] **Step 2: Viết test cho Library (sẽ fail)**

`tests/test_db.py`:

```python
from dataclasses import dataclass

import pytest

from stories_crawl.storage.db import Library


@dataclass
class Ref:
    idx: int
    title: str
    url: str


@pytest.fixture
def lib(tmp_path):
    lib = Library(tmp_path / "library.db")
    yield lib
    lib.close()


def _add_novel(lib):
    return lib.create_novel(
        slug="斗破苍穹", title="斗破苍穹", author="天蚕土豆",
        source_url="https://example.com/book/1", adapter="lncrawl",
    )


def test_create_and_get_novel(lib):
    novel_id = _add_novel(lib)
    row = lib.get_novel_by_url("https://example.com/book/1")
    assert row["id"] == novel_id
    assert row["title"] == "斗破苍穹"
    assert row["status"] == "active"
    assert lib.get_novel(str(novel_id))["slug"] == "斗破苍穹"
    assert lib.get_novel("斗破苍穹")["id"] == novel_id
    assert lib.get_novel("không-tồn-tại") is None
    assert lib.existing_slugs() == {"斗破苍穹"}


def test_add_chapters_idempotent(lib):
    novel_id = _add_novel(lib)
    chapters = [Ref(1, "第一章", "https://example.com/c/1"),
                Ref(2, "第二章", "https://example.com/c/2")]
    assert lib.add_chapters(novel_id, chapters) == 2
    # thêm lại + 1 chương mới → chỉ chèn 1
    chapters.append(Ref(3, "第三章", "https://example.com/c/3"))
    assert lib.add_chapters(novel_id, chapters) == 1


def test_pending_and_status_transitions(lib):
    novel_id = _add_novel(lib)
    lib.add_chapters(novel_id, [Ref(1, "第一章", "https://example.com/c/1"),
                                Ref(2, "第二章", "https://example.com/c/2")])
    pending = lib.pending_chapters(novel_id)
    assert [r["idx"] for r in pending] == [1, 2]

    lib.mark_chapter_done(pending[0]["id"], "斗破苍穹/raw/0001-第一章.md")
    lib.mark_chapter_failed(pending[1]["id"], "timeout")

    # failed vẫn nằm trong pending (để retry), done thì không
    remaining = lib.pending_chapters(novel_id)
    assert [r["idx"] for r in remaining] == [2]
    assert remaining[0]["error"] == "timeout"


def test_list_novels_progress(lib):
    novel_id = _add_novel(lib)
    lib.add_chapters(novel_id, [Ref(1, "第一章", "https://example.com/c/1"),
                                Ref(2, "第二章", "https://example.com/c/2")])
    ch = lib.pending_chapters(novel_id)[0]
    lib.mark_chapter_done(ch["id"], "x.md")
    rows = lib.list_novels()
    assert len(rows) == 1
    assert rows[0]["total_count"] == 2
    assert rows[0]["done_count"] == 1
```

- [ ] **Step 3: Chạy test, xác nhận fail**

Run: `.venv/bin/pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stories_crawl.storage.db'`

- [ ] **Step 4: Viết stories_crawl/storage/db.py**

```python
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS novels (
  id INTEGER PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  author TEXT,
  source_url TEXT UNIQUE NOT NULL,
  adapter TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chapters (
  id INTEGER PRIMARY KEY,
  novel_id INTEGER NOT NULL REFERENCES novels(id),
  idx INTEGER NOT NULL,
  title TEXT,
  source_url TEXT NOT NULL,
  file_path TEXT,
  crawl_status TEXT NOT NULL,
  error TEXT,
  updated_at TEXT NOT NULL,
  UNIQUE(novel_id, idx)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Library:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        with self.conn:
            self.conn.executescript(SCHEMA)

    def close(self):
        self.conn.close()

    def create_novel(self, slug, title, author, source_url, adapter) -> int:
        now = _now()
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO novels"
                " (slug, title, author, source_url, adapter, status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, 'active', ?, ?)",
                (slug, title, author, source_url, adapter, now, now),
            )
        return cur.lastrowid

    def get_novel_by_url(self, url):
        return self.conn.execute(
            "SELECT * FROM novels WHERE source_url = ?", (url,)
        ).fetchone()

    def get_novel(self, key):
        if str(key).isdigit():
            row = self.conn.execute(
                "SELECT * FROM novels WHERE id = ?", (int(key),)
            ).fetchone()
            if row:
                return row
        return self.conn.execute(
            "SELECT * FROM novels WHERE slug = ?", (str(key),)
        ).fetchone()

    def existing_slugs(self) -> set:
        return {r["slug"] for r in self.conn.execute("SELECT slug FROM novels")}

    def add_chapters(self, novel_id, chapters) -> int:
        now = _now()
        inserted = 0
        with self.conn:
            for ch in chapters:
                cur = self.conn.execute(
                    "INSERT OR IGNORE INTO chapters"
                    " (novel_id, idx, title, source_url, crawl_status, updated_at)"
                    " VALUES (?, ?, ?, ?, 'pending', ?)",
                    (novel_id, ch.idx, ch.title, ch.url, now),
                )
                inserted += cur.rowcount
        return inserted

    def pending_chapters(self, novel_id):
        return self.conn.execute(
            "SELECT * FROM chapters"
            " WHERE novel_id = ? AND crawl_status IN ('pending', 'failed')"
            " ORDER BY idx",
            (novel_id,),
        ).fetchall()

    def mark_chapter_done(self, chapter_id, file_path):
        with self.conn:
            self.conn.execute(
                "UPDATE chapters SET crawl_status = 'done', file_path = ?,"
                " error = NULL, updated_at = ? WHERE id = ?",
                (file_path, _now(), chapter_id),
            )

    def mark_chapter_failed(self, chapter_id, error):
        with self.conn:
            self.conn.execute(
                "UPDATE chapters SET crawl_status = 'failed', error = ?,"
                " updated_at = ? WHERE id = ?",
                (error, _now(), chapter_id),
            )

    def touch_novel(self, novel_id):
        with self.conn:
            self.conn.execute(
                "UPDATE novels SET updated_at = ? WHERE id = ?", (_now(), novel_id)
            )

    def list_novels(self):
        return self.conn.execute(
            "SELECT n.*,"
            " COUNT(c.id) AS total_count,"
            " COALESCE(SUM(CASE WHEN c.crawl_status = 'done' THEN 1 ELSE 0 END), 0)"
            "   AS done_count"
            " FROM novels n LEFT JOIN chapters c ON c.novel_id = n.id"
            " GROUP BY n.id ORDER BY n.updated_at DESC"
        ).fetchall()
```

- [ ] **Step 5: Chạy test, xác nhận pass**

Run: `.venv/bin/pytest tests/test_db.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore stories_crawl tests/test_db.py
git commit -m "feat: project scaffolding and SQLite library storage"
```

---

### Task 2: storage/files.py

**Files:**
- Create: `stories_crawl/storage/files.py`
- Test: `tests/test_files.py`

**Interfaces:**
- Consumes: (không có)
- Produces: trong `stories_crawl/storage/files.py`:
  - `sanitize(name: str) -> str` — thay `/ \ : * ? " < > |` và khoảng trắng bằng `-`, gộp liên tiếp, cắt `-` hai đầu; rỗng → `"untitled"`
  - `make_slug(title: str, existing: set[str]) -> str` — sanitize + hậu tố `-2`, `-3`... nếu trùng
  - `chapter_filename(idx: int, title: str) -> str` — `f"{idx:04d}-{sanitize(title)}.md"`
  - `write_chapter(library_dir: Path, slug: str, idx: int, title: str, text: str) -> str` — ghi `# <title>\n\n<text>\n` (bỏ dòng heading nếu title rỗng) vào `<slug>/raw/<filename>`, ghi qua file tạm rồi rename; trả về đường dẫn tương đối từ library_dir (dạng chuỗi POSIX)

- [ ] **Step 1: Viết test (sẽ fail)**

`tests/test_files.py`:

```python
from pathlib import Path

from stories_crawl.storage.files import (
    chapter_filename,
    make_slug,
    sanitize,
    write_chapter,
)


def test_sanitize():
    assert sanitize("斗破苍穹") == "斗破苍穹"
    assert sanitize('a/b\\c:d*e?f"g<h>i|j') == "a-b-c-d-e-f-g-h-i-j"
    assert sanitize("  第 一 章  ") == "第-一-章"
    assert sanitize("///") == "untitled"


def test_make_slug_unique():
    assert make_slug("斗破苍穹", set()) == "斗破苍穹"
    assert make_slug("斗破苍穹", {"斗破苍穹"}) == "斗破苍穹-2"
    assert make_slug("斗破苍穹", {"斗破苍穹", "斗破苍穹-2"}) == "斗破苍穹-3"


def test_chapter_filename():
    assert chapter_filename(1, "第一章 陨落的天才") == "0001-第一章-陨落的天才.md"
    assert chapter_filename(12345, "第12345章") == "12345-第12345章.md"


def test_write_chapter(tmp_path):
    rel = write_chapter(tmp_path, "斗破苍穹", 1, "第一章", "内容" * 100)
    assert rel == "斗破苍穹/raw/0001-第一章.md"
    content = (tmp_path / rel).read_text(encoding="utf-8")
    assert content.startswith("# 第一章\n\n内容")
    assert content.endswith("\n")
    # không còn file tạm sót lại
    assert list((tmp_path / "斗破苍穹" / "raw").glob("*.tmp")) == []


def test_write_chapter_overwrites(tmp_path):
    write_chapter(tmp_path, "s", 1, "t", "cũ")
    rel = write_chapter(tmp_path, "s", 1, "t", "mới")
    assert "mới" in (tmp_path / rel).read_text(encoding="utf-8")
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `.venv/bin/pytest tests/test_files.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Viết stories_crawl/storage/files.py**

```python
import re
from pathlib import Path

_INVALID = re.compile(r'[\\/:*?"<>|\s]+')


def sanitize(name: str) -> str:
    cleaned = _INVALID.sub("-", name).strip("-")
    return cleaned or "untitled"


def make_slug(title: str, existing: set) -> str:
    base = sanitize(title)
    slug = base
    n = 2
    while slug in existing:
        slug = f"{base}-{n}"
        n += 1
    return slug


def chapter_filename(idx: int, title: str) -> str:
    return f"{idx:04d}-{sanitize(title)}.md"


def write_chapter(library_dir: Path, slug: str, idx: int, title: str, text: str) -> str:
    rel = Path(slug) / "raw" / chapter_filename(idx, title)
    path = library_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"# {title}\n\n{text}\n" if title else f"{text}\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
    return rel.as_posix()
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `.venv/bin/pytest tests/test_files.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add stories_crawl/storage/files.py tests/test_files.py
git commit -m "feat: markdown file storage with slug and atomic write"
```

---

### Task 3: adapters/base.py + core/registry.py

**Files:**
- Create: `stories_crawl/adapters/__init__.py`, `stories_crawl/adapters/base.py`, `stories_crawl/adapters/native/__init__.py`, `stories_crawl/core/__init__.py`, `stories_crawl/core/registry.py`
- Test: `tests/test_registry.py`

**Interfaces:**
- Consumes: (không có)
- Produces:
  - `stories_crawl/adapters/base.py`: `@dataclass ChapterRef(idx: int, title: str, url: str)`; `@dataclass NovelInfo(title: str, author: str, url: str, chapters: list[ChapterRef])`; `class UnsupportedSourceError(Exception)`; `class BaseAdapter(ABC)` với `__init__(self, url: str)` (lưu `self.url`), classmethod trừu tượng `supports(cls, url: str) -> bool`, method trừu tượng `get_novel_info(self, url: str) -> NovelInfo` và `get_chapter(self, chapter_url: str) -> str` (trả plain text), method thường `close(self) -> None` (mặc định no-op), thuộc tính class `name: str = "base"`
  - `stories_crawl/core/registry.py`: `NATIVE_ADAPTERS: list[type[BaseAdapter]]` (rỗng); `find_adapter_class(url: str) -> type[BaseAdapter]` — duyệt native trước, rồi `LncrawlAdapter` (import bên trong hàm để test patch được), không match → raise `UnsupportedSourceError`

- [ ] **Step 1: Viết test (sẽ fail)**

`tests/test_registry.py`:

```python
import pytest

from stories_crawl.adapters.base import (
    BaseAdapter,
    ChapterRef,
    NovelInfo,
    UnsupportedSourceError,
)
from stories_crawl.core import registry


class FakeNative(BaseAdapter):
    name = "fake-native"

    @classmethod
    def supports(cls, url):
        return "fake-site.com" in url

    def get_novel_info(self, url):
        return NovelInfo(title="t", author="a", url=url,
                         chapters=[ChapterRef(1, "c1", url + "/1")])

    def get_chapter(self, chapter_url):
        return "nội dung"


@pytest.fixture(autouse=True)
def clean_natives(monkeypatch):
    monkeypatch.setattr(registry, "NATIVE_ADAPTERS", [FakeNative])


def test_native_adapter_wins(monkeypatch):
    # lncrawl bridge không được gọi khi native đã match
    monkeypatch.setattr(
        "stories_crawl.adapters.lncrawl_bridge.LncrawlAdapter.supports",
        classmethod(lambda cls, url: (_ for _ in ()).throw(AssertionError("not called"))),
    )
    assert registry.find_adapter_class("https://fake-site.com/book/1") is FakeNative


def test_fallback_to_lncrawl(monkeypatch):
    monkeypatch.setattr(
        "stories_crawl.adapters.lncrawl_bridge.LncrawlAdapter.supports",
        classmethod(lambda cls, url: True),
    )
    from stories_crawl.adapters.lncrawl_bridge import LncrawlAdapter
    assert registry.find_adapter_class("https://other.com/x") is LncrawlAdapter


def test_unsupported_raises(monkeypatch):
    monkeypatch.setattr(
        "stories_crawl.adapters.lncrawl_bridge.LncrawlAdapter.supports",
        classmethod(lambda cls, url: False),
    )
    with pytest.raises(UnsupportedSourceError):
        registry.find_adapter_class("https://unknown.org/x")
```

Lưu ý: test này cần `lncrawl_bridge.py` tồn tại (Task 4 viết logic thật; ở task này chỉ cần class có mặt). Vì vậy Step 2 tạo luôn skeleton bridge tối thiểu.

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `.venv/bin/pytest tests/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Viết base.py, registry.py và skeleton bridge**

`stories_crawl/adapters/base.py`:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ChapterRef:
    idx: int
    title: str
    url: str


@dataclass
class NovelInfo:
    title: str
    author: str
    url: str
    chapters: list = field(default_factory=list)


class UnsupportedSourceError(Exception):
    pass


class BaseAdapter(ABC):
    name: str = "base"

    def __init__(self, url: str):
        self.url = url

    @classmethod
    @abstractmethod
    def supports(cls, url: str) -> bool: ...

    @abstractmethod
    def get_novel_info(self, url: str) -> NovelInfo: ...

    @abstractmethod
    def get_chapter(self, chapter_url: str) -> str: ...

    def close(self) -> None:
        pass
```

`stories_crawl/core/registry.py`:

```python
from ..adapters.base import UnsupportedSourceError

NATIVE_ADAPTERS: list = []


def find_adapter_class(url: str):
    for cls in NATIVE_ADAPTERS:
        if cls.supports(url):
            return cls
    from ..adapters.lncrawl_bridge import LncrawlAdapter

    if LncrawlAdapter.supports(url):
        return LncrawlAdapter
    raise UnsupportedSourceError(f"Không có adapter nào hỗ trợ: {url}")
```

`stories_crawl/adapters/lncrawl_bridge.py` (skeleton, Task 4 hoàn thiện):

```python
from .base import BaseAdapter, ChapterRef, NovelInfo


class LncrawlAdapter(BaseAdapter):
    name = "lncrawl"

    @classmethod
    def supports(cls, url: str) -> bool:
        raise NotImplementedError

    def get_novel_info(self, url: str) -> NovelInfo:
        raise NotImplementedError

    def get_chapter(self, chapter_url: str) -> str:
        raise NotImplementedError
```

`stories_crawl/adapters/__init__.py`, `stories_crawl/adapters/native/__init__.py`, `stories_crawl/core/__init__.py`: file trống.

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `.venv/bin/pytest tests/test_registry.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add stories_crawl/adapters stories_crawl/core tests/test_registry.py
git commit -m "feat: adapter interface and URL-based adapter registry"
```

---

### Task 4: adapters/lncrawl_bridge.py

**Files:**
- Modify: `stories_crawl/adapters/lncrawl_bridge.py` (thay skeleton bằng logic thật)
- Test: `tests/test_lncrawl_bridge.py`

**Interfaces:**
- Consumes: `BaseAdapter`, `ChapterRef`, `NovelInfo` từ Task 3
- Produces: trong `stories_crawl/adapters/lncrawl_bridge.py`:
  - `_sources()` — nạp registry nguồn lncrawl một lần (module-level cache), trả về `ctx.sources`. Test patch hàm này.
  - `list_supported_domains(language: str = "zh") -> list[str]` — domain đã sort, lọc theo `file_path` bắt đầu `sources/<language>/`, bỏ nguồn `is_disabled`
  - `class LncrawlAdapter(BaseAdapter)` — `name = "lncrawl"`; `__init__` gọi `_sources().init_crawler(url)`; `supports()` dùng `find_crawler`; `get_novel_info()` trả `NovelInfo` và cache map url→Chapter nội bộ; `get_chapter(url)` tải rồi trả plain text (strip HTML bằng BeautifulSoup); `close()` đóng crawler, nuốt lỗi

- [ ] **Step 1: Viết test (sẽ fail)**

`tests/test_lncrawl_bridge.py`:

```python
from types import SimpleNamespace

import pytest

from stories_crawl.adapters import lncrawl_bridge
from stories_crawl.adapters.lncrawl_bridge import (
    LncrawlAdapter,
    list_supported_domains,
)


class FakeChapter(SimpleNamespace):
    pass


class FakeCrawler:
    def __init__(self):
        self.closed = False

    def read_novel(self, novel):
        novel.title = "斗破苍穹"
        novel.author = "天蚕土豆"
        novel.chapters = [
            FakeChapter(id=1, url="https://x.com/c/1", title="第一章", body=None),
            FakeChapter(id=2, url="https://x.com/c/2", title="第二章", body=None),
        ]

    def download_chapter(self, chapter):
        chapter.body = "<p>你好</p><p>世界</p>"

    def close(self):
        self.closed = True


class FakeSources:
    def __init__(self):
        self.crawler = FakeCrawler()

    def find_crawler(self, url):
        if "supported.com" not in url:
            raise ValueError("no crawler")
        return FakeCrawler

    def init_crawler(self, url):
        return self.crawler

    def list(self):
        return [
            SimpleNamespace(domain="69shuba.com", file_path="sources/zh/69shuba.py",
                            is_disabled=False),
            SimpleNamespace(domain="dead.com", file_path="sources/zh/dead.py",
                            is_disabled=True),
            SimpleNamespace(domain="royalroad.com", file_path="sources/en/r/royalroad.py",
                            is_disabled=False),
        ]


@pytest.fixture
def fake_sources(monkeypatch):
    fake = FakeSources()
    monkeypatch.setattr(lncrawl_bridge, "_sources", lambda: fake)
    return fake


def test_supports(fake_sources):
    assert LncrawlAdapter.supports("https://supported.com/book/1") is True
    assert LncrawlAdapter.supports("https://nope.com/book/1") is False


def test_get_novel_info(fake_sources):
    adapter = LncrawlAdapter("https://supported.com/book/1")
    info = adapter.get_novel_info("https://supported.com/book/1")
    assert info.title == "斗破苍穹"
    assert info.author == "天蚕土豆"
    assert [(c.idx, c.title, c.url) for c in info.chapters] == [
        (1, "第一章", "https://x.com/c/1"),
        (2, "第二章", "https://x.com/c/2"),
    ]


def test_get_chapter_strips_html(fake_sources):
    adapter = LncrawlAdapter("https://supported.com/book/1")
    adapter.get_novel_info("https://supported.com/book/1")
    text = adapter.get_chapter("https://x.com/c/1")
    assert "你好" in text and "世界" in text
    assert "<p>" not in text


def test_close_swallows_errors(fake_sources):
    adapter = LncrawlAdapter("https://supported.com/book/1")
    adapter.close()
    assert fake_sources.crawler.closed is True
    fake_sources.crawler.close = lambda: (_ for _ in ()).throw(RuntimeError)
    adapter.close()  # không raise


def test_list_supported_domains(fake_sources):
    assert list_supported_domains() == ["69shuba.com"]
    assert list_supported_domains("en") == ["royalroad.com"]
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `.venv/bin/pytest tests/test_lncrawl_bridge.py -v`
Expected: FAIL — `NotImplementedError` / `AttributeError: _sources`

- [ ] **Step 3: Viết bridge hoàn chỉnh**

Thay toàn bộ `stories_crawl/adapters/lncrawl_bridge.py`:

```python
import threading

from bs4 import BeautifulSoup

from .base import BaseAdapter, ChapterRef, NovelInfo

_lock = threading.Lock()
_loaded = False


def _sources():
    """Nạp registry nguồn của lncrawl (lần đầu chạy sẽ sync index từ GitHub)."""
    global _loaded
    from lncrawl.context import ctx

    with _lock:
        if not _loaded:
            ctx.sources.load(sync_remote=True)
            ctx.sources.ensure_load()
            _loaded = True
    return ctx.sources


def list_supported_domains(language: str = "zh") -> list:
    prefix = f"sources/{language}/"
    items = _sources().list()
    return sorted(
        i.domain
        for i in items
        if i.file_path.startswith(prefix) and not i.is_disabled
    )


class LncrawlAdapter(BaseAdapter):
    name = "lncrawl"

    def __init__(self, url: str):
        super().__init__(url)
        self._crawler = _sources().init_crawler(url)
        self._chapter_map = {}

    @classmethod
    def supports(cls, url: str) -> bool:
        try:
            _sources().find_crawler(url)
            return True
        except Exception:
            return False

    def get_novel_info(self, url: str) -> NovelInfo:
        from lncrawl.core import Novel

        novel = Novel(url=url)
        self._crawler.read_novel(novel)
        refs = []
        for ch in novel.chapters:
            self._chapter_map[ch.url] = ch
            refs.append(ChapterRef(idx=ch.id, title=ch.title or "", url=ch.url))
        return NovelInfo(
            title=novel.title, author=novel.author or "", url=url, chapters=refs
        )

    def get_chapter(self, chapter_url: str) -> str:
        ch = self._chapter_map[chapter_url]
        self._crawler.download_chapter(ch)
        html = ch.body or ""
        return BeautifulSoup(html, "html.parser").get_text("\n").strip()

    def close(self) -> None:
        try:
            self._crawler.close()
        except Exception:
            pass
```

- [ ] **Step 4: Chạy test, xác nhận pass (kèm test cũ)**

Run: `.venv/bin/pytest tests/ -v`
Expected: tất cả pass (test_db 4, test_files 5, test_registry 3, test_lncrawl_bridge 5)

- [ ] **Step 5: Commit**

```bash
git add stories_crawl/adapters/lncrawl_bridge.py tests/test_lncrawl_bridge.py
git commit -m "feat: lightnovel-crawler bridge adapter"
```

---

### Task 5: core/downloader.py

**Files:**
- Create: `stories_crawl/core/downloader.py`, `tests/conftest.py`
- Test: `tests/test_downloader.py`

**Interfaces:**
- Consumes: `Library` (Task 1), `write_chapter` (Task 2), `BaseAdapter`/`NovelInfo`/`ChapterRef` (Task 3)
- Produces:
  - `stories_crawl/core/downloader.py`: `class ContentTooShortError(Exception)`; `@dataclass DownloadSummary(done: int = 0, failed: int = 0, failures: list = [])` — failures là list tuple `(idx, title, error)`; hàm `download_pending(adapter, lib, library_dir: Path, novel, *, delay_range=(1.0, 2.0), max_retries=3, min_length=200, sleep=time.sleep, log=print) -> DownloadSummary` — novel là sqlite3.Row (cần `id`, `slug`)
  - `tests/conftest.py`: `class FakeAdapter(BaseAdapter)` dùng chung cho test downloader + CLI, có `name = "fake"`, khởi tạo với dict `chapters: {url: text}`, đếm số lần gọi trong `self.calls`, raise `FakeNetworkError` cho URL nằm trong `fail_urls` (fail `fail_times` lần đầu rồi thành công)

- [ ] **Step 1: Viết conftest.py**

`tests/conftest.py`:

```python
from stories_crawl.adapters.base import BaseAdapter, ChapterRef, NovelInfo


class FakeNetworkError(Exception):
    pass


class FakeAdapter(BaseAdapter):
    """Adapter giả cho test: nội dung cấp sẵn, có thể giả lập lỗi mạng."""

    name = "fake"

    def __init__(self, url="https://fake-site.com/book/1", chapters=None,
                 fail_urls=(), fail_times=99):
        super().__init__(url)
        default = {
            "https://fake-site.com/c/1": "một " * 100,
            "https://fake-site.com/c/2": "hai " * 100,
        }
        self.chapters = chapters if chapters is not None else default
        self.fail_urls = set(fail_urls)
        self.fail_times = fail_times
        self.calls = {}
        self.closed = False

    @classmethod
    def supports(cls, url):
        return "fake-site.com" in url

    def get_novel_info(self, url):
        refs = [
            ChapterRef(i + 1, f"Chương {i + 1}", u)
            for i, u in enumerate(self.chapters)
        ]
        return NovelInfo(title="Truyện Giả", author="Tác Giả", url=url, chapters=refs)

    def get_chapter(self, chapter_url):
        self.calls[chapter_url] = self.calls.get(chapter_url, 0) + 1
        if chapter_url in self.fail_urls and self.calls[chapter_url] <= self.fail_times:
            raise FakeNetworkError("connection reset")
        return self.chapters[chapter_url]

    def close(self):
        self.closed = True
```

- [ ] **Step 2: Viết test downloader (sẽ fail)**

`tests/test_downloader.py`:

```python
import pytest

from stories_crawl.core.downloader import download_pending
from stories_crawl.storage.db import Library

from conftest import FakeAdapter


@pytest.fixture
def env(tmp_path):
    lib = Library(tmp_path / "library.db")
    adapter = FakeAdapter()
    info = adapter.get_novel_info(adapter.url)
    novel_id = lib.create_novel("truyen-gia", info.title, info.author,
                                adapter.url, adapter.name)
    lib.add_chapters(novel_id, info.chapters)
    novel = lib.get_novel(str(novel_id))
    yield tmp_path, lib, adapter, novel
    lib.close()


def _no_sleep(_):
    pass


def test_downloads_all_pending(env):
    tmp_path, lib, adapter, novel = env
    summary = download_pending(adapter, lib, tmp_path, novel,
                               sleep=_no_sleep, log=lambda *_: None)
    assert (summary.done, summary.failed) == (2, 0)
    assert lib.pending_chapters(novel["id"]) == []
    f = tmp_path / "truyen-gia" / "raw" / "0001-Chương-1.md"
    assert f.read_text(encoding="utf-8").startswith("# Chương 1")


def test_retry_then_success(env):
    tmp_path, lib, adapter, novel = env
    adapter.fail_urls = {"https://fake-site.com/c/1"}
    adapter.fail_times = 2  # fail 2 lần đầu, lần 3 OK
    summary = download_pending(adapter, lib, tmp_path, novel,
                               sleep=_no_sleep, log=lambda *_: None)
    assert (summary.done, summary.failed) == (2, 0)
    assert adapter.calls["https://fake-site.com/c/1"] == 3


def test_exhausted_retries_marks_failed(env):
    tmp_path, lib, adapter, novel = env
    adapter.fail_urls = {"https://fake-site.com/c/2"}  # luôn fail
    summary = download_pending(adapter, lib, tmp_path, novel,
                               sleep=_no_sleep, log=lambda *_: None)
    assert (summary.done, summary.failed) == (1, 1)
    assert summary.failures[0][0] == 2
    assert "connection reset" in summary.failures[0][2]
    # chương failed vẫn pending để lần sau retry
    assert [r["idx"] for r in lib.pending_chapters(novel["id"])] == [2]
    # file của chương failed không được tạo
    assert not (tmp_path / "truyen-gia" / "raw" / "0002-Chương-2.md").exists()


def test_short_content_marks_failed(env):
    tmp_path, lib, adapter, novel = env
    adapter.chapters["https://fake-site.com/c/1"] = "ngắn"
    summary = download_pending(adapter, lib, tmp_path, novel,
                               sleep=_no_sleep, log=lambda *_: None)
    assert (summary.done, summary.failed) == (1, 1)
    assert not (tmp_path / "truyen-gia" / "raw" / "0001-Chương-1.md").exists()


def test_resume_skips_done(env):
    tmp_path, lib, adapter, novel = env
    download_pending(adapter, lib, tmp_path, novel,
                     sleep=_no_sleep, log=lambda *_: None)
    adapter.calls.clear()
    summary = download_pending(adapter, lib, tmp_path, novel,
                               sleep=_no_sleep, log=lambda *_: None)
    assert (summary.done, summary.failed) == (0, 0)
    assert adapter.calls == {}
```

- [ ] **Step 3: Chạy test, xác nhận fail**

Run: `.venv/bin/pytest tests/test_downloader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stories_crawl.core.downloader'`

- [ ] **Step 4: Viết stories_crawl/core/downloader.py**

```python
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..storage.files import write_chapter


class ContentTooShortError(Exception):
    pass


@dataclass
class DownloadSummary:
    done: int = 0
    failed: int = 0
    failures: list = field(default_factory=list)


def download_pending(adapter, lib, library_dir: Path, novel, *,
                     delay_range=(1.0, 2.0), max_retries=3, min_length=200,
                     sleep=time.sleep, log=print) -> DownloadSummary:
    summary = DownloadSummary()
    chapters = lib.pending_chapters(novel["id"])
    for i, ch in enumerate(chapters):
        last_error = ""
        for attempt in range(1, max_retries + 1):
            try:
                text = adapter.get_chapter(ch["source_url"])
                if len(text) < min_length:
                    raise ContentTooShortError(
                        f"Nội dung quá ngắn ({len(text)} ký tự), có thể bị chặn"
                    )
                rel = write_chapter(
                    library_dir, novel["slug"], ch["idx"], ch["title"] or "", text
                )
                lib.mark_chapter_done(ch["id"], rel)
                summary.done += 1
                log(f"  [{ch['idx']:>5}] {ch['title']} — OK")
                break
            except Exception as e:
                last_error = str(e) or type(e).__name__
                if attempt < max_retries:
                    sleep(2 ** (attempt - 1))
        else:
            lib.mark_chapter_failed(ch["id"], last_error)
            summary.failed += 1
            summary.failures.append((ch["idx"], ch["title"] or "", last_error))
            log(f"  [{ch['idx']:>5}] {ch['title']} — LỖI: {last_error}")
        if i < len(chapters) - 1:
            sleep(random.uniform(*delay_range))
    lib.touch_novel(novel["id"])
    return summary
```

- [ ] **Step 5: Chạy test, xác nhận pass**

Run: `.venv/bin/pytest tests/test_downloader.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add stories_crawl/core/downloader.py tests/conftest.py tests/test_downloader.py
git commit -m "feat: chapter download loop with retry, resume, and delay"
```

---

### Task 6: cli.py

**Files:**
- Create: `stories_crawl/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `Library` (Task 1), `make_slug` (Task 2), `registry.find_adapter_class` (Task 3), `list_supported_domains` (Task 4), `download_pending` (Task 5), `FakeAdapter` từ `tests/conftest.py` (Task 5)
- Produces: `stories_crawl/cli.py` với click group `main` và 4 lệnh: `add <url>`, `update <key>`, `list`, `sources`. Thư mục kho lấy từ env `STORIES_LIBRARY`, mặc định `library`. Đây là entry point của console script `crawl` (đã khai báo ở Task 1).

- [ ] **Step 1: Viết test (sẽ fail)**

`tests/test_cli.py`:

```python
import pytest
from click.testing import CliRunner

from stories_crawl.cli import main
from stories_crawl.core import registry
from stories_crawl.storage.db import Library

from conftest import FakeAdapter


@pytest.fixture
def runner(tmp_path, monkeypatch):
    monkeypatch.setenv("STORIES_LIBRARY", str(tmp_path / "library"))
    monkeypatch.setattr(registry, "NATIVE_ADAPTERS", [FakeAdapter])
    # downloader chạy thật nhưng không ngủ
    monkeypatch.setattr("stories_crawl.cli.DOWNLOAD_KWARGS", {"sleep": lambda _: None})
    return CliRunner(), tmp_path / "library"


def test_add_downloads_novel(runner):
    cli, lib_dir = runner
    result = cli.invoke(main, ["add", "https://fake-site.com/book/1"])
    assert result.exit_code == 0, result.output
    assert "Truyện Giả" in result.output
    assert "2 OK, 0 lỗi" in result.output
    assert (lib_dir / "Truyện-Giả" / "raw" / "0001-Chương-1.md").exists()


def test_add_existing_url_resumes(runner):
    cli, lib_dir = runner
    cli.invoke(main, ["add", "https://fake-site.com/book/1"])
    result = cli.invoke(main, ["add", "https://fake-site.com/book/1"])
    assert result.exit_code == 0, result.output
    assert "0 OK, 0 lỗi" in result.output  # không tải lại chương đã done


def test_update_by_slug_and_id(runner):
    cli, lib_dir = runner
    cli.invoke(main, ["add", "https://fake-site.com/book/1"])
    result = cli.invoke(main, ["update", "Truyện-Giả"])
    assert result.exit_code == 0, result.output
    result = cli.invoke(main, ["update", "1"])
    assert result.exit_code == 0, result.output


def test_update_unknown_novel(runner):
    cli, _ = runner
    result = cli.invoke(main, ["update", "không-có"])
    assert result.exit_code != 0
    assert "Không tìm thấy" in result.output


def test_list_shows_progress(runner):
    cli, _ = runner
    cli.invoke(main, ["add", "https://fake-site.com/book/1"])
    result = cli.invoke(main, ["list"])
    assert result.exit_code == 0, result.output
    assert "Truyện Giả" in result.output
    assert "2/2" in result.output


def test_list_empty(runner):
    cli, _ = runner
    result = cli.invoke(main, ["list"])
    assert result.exit_code == 0
    assert "Kho trống" in result.output


def test_sources(runner, monkeypatch):
    cli, _ = runner
    monkeypatch.setattr(
        "stories_crawl.adapters.lncrawl_bridge.list_supported_domains",
        lambda language="zh": ["69shuba.com", "uukanshu.cc"],
    )
    result = cli.invoke(main, ["sources"])
    assert result.exit_code == 0, result.output
    assert "69shuba.com" in result.output
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stories_crawl.cli'`

- [ ] **Step 3: Viết stories_crawl/cli.py**

```python
import os
from pathlib import Path

import click

from .core import registry
from .core.downloader import download_pending
from .storage.db import Library
from .storage.files import make_slug

# test ghi đè để tắt sleep; runtime để trống dùng mặc định
DOWNLOAD_KWARGS: dict = {}


def _library_dir() -> Path:
    return Path(os.environ.get("STORIES_LIBRARY", "library"))


@click.group()
def main():
    """stories-crawl — thu thập truyện về kho cá nhân."""


def _crawl(lib: Library, lib_dir: Path, url: str, existing=None):
    adapter_cls = registry.find_adapter_class(url)
    adapter = adapter_cls(url)
    try:
        click.echo(f"Đang lấy mục lục: {url}")
        info = adapter.get_novel_info(url)
        row = existing or lib.get_novel_by_url(url)
        if row is None:
            slug = make_slug(info.title, lib.existing_slugs())
            lib.create_novel(slug, info.title, info.author, url, adapter_cls.name)
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
    finally:
        adapter.close()


@main.command()
@click.argument("url")
def add(url):
    """Thêm truyện mới vào kho và tải toàn bộ chương."""
    lib_dir = _library_dir()
    lib = Library(lib_dir / "library.db")
    try:
        _crawl(lib, lib_dir, url)
    finally:
        lib.close()


@main.command()
@click.argument("key")
def update(key):
    """Tải các chương mới/còn thiếu của truyện đã có (theo slug hoặc id)."""
    lib_dir = _library_dir()
    lib = Library(lib_dir / "library.db")
    try:
        row = lib.get_novel(key)
        if row is None:
            raise click.ClickException(f"Không tìm thấy truyện: {key}")
        _crawl(lib, lib_dir, row["source_url"], existing=row)
    finally:
        lib.close()


@main.command("list")
def list_cmd():
    """Liệt kê truyện trong kho kèm tiến độ."""
    lib_dir = _library_dir()
    lib = Library(lib_dir / "library.db")
    try:
        rows = lib.list_novels()
        if not rows:
            click.echo("Kho trống.")
            return
        for r in rows:
            click.echo(
                f"[{r['id']}] {r['title']} ({r['slug']})"
                f" — {r['done_count']}/{r['total_count']} chương — {r['status']}"
            )
    finally:
        lib.close()


@main.command()
def sources():
    """Liệt kê các domain tiếng Trung được hỗ trợ."""
    from .adapters import lncrawl_bridge

    for domain in lncrawl_bridge.list_supported_domains():
        click.echo(domain)
```

Lưu ý cho test `test_sources`: lệnh `sources` phải gọi `lncrawl_bridge.list_supported_domains` qua module attribute (như trên) — monkeypatch mới có tác dụng.

- [ ] **Step 4: Chạy toàn bộ test, xác nhận pass**

Run: `.venv/bin/pytest tests/ -v`
Expected: tất cả pass (4+5+3+5+5+7 = 29 test)

- [ ] **Step 5: Commit**

```bash
git add stories_crawl/cli.py tests/test_cli.py
git commit -m "feat: CLI commands add, update, list, sources"
```

---

### Task 7: Smoke test thật + README

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: toàn bộ tool đã hoàn thiện
- Produces: xác nhận tool chạy được với trang thật; tài liệu sử dụng

- [ ] **Step 1: Smoke test với truyện thật**

Chọn một truyện ngắn (vài chục chương) trên 69shuba. Vào https://www.69shuba.com tìm 1 truyện đã hoàn thành ít chương, copy URL trang giới thiệu truyện. Chạy:

```bash
.venv/bin/crawl sources          # phải in ra ~24 domain zh
.venv/bin/crawl add '<URL truyện>'
.venv/bin/crawl list
```

Kiểm tra:
- `library/<slug>/raw/` có file `.md` cho từng chương, mở 1 file xem nội dung là văn bản tiếng Trung sạch (không còn HTML).
- Ctrl-C giữa chừng rồi chạy `crawl update <slug>` → tiếp tục từ chỗ dừng, không tải lại chương đã có.
- `crawl list` hiện đúng tiến độ.

Nếu bị chặn (nhiều chương failed liên tiếp với nội dung ngắn): thử domain khác trong `crawl sources` (69shu.pro, ixdzs8.com...). Ghi lại kết quả vào commit message.

- [ ] **Step 2: Viết README.md**

```markdown
# stories-crawl

CLI thu thập truyện tiếng Trung về kho cá nhân, lưu dạng markdown + SQLite.
Dùng [lightnovel-crawler](https://github.com/dipu-bd/lightnovel-crawler) làm
engine cho ~24 trang nguồn tiếng Trung (69shuba, ixdzs, piaotian...).

## Cài đặt

    python3 -m venv .venv
    .venv/bin/pip install -e .

## Sử dụng

    crawl sources                # các domain được hỗ trợ
    crawl add <url-trang-truyện> # tải truyện mới về kho
    crawl update <slug|id>       # tải tiếp chương mới/chương lỗi
    crawl list                   # danh sách truyện + tiến độ

Kho mặc định là `./library` (đổi bằng biến môi trường `STORIES_LIBRARY`):

    library/
    ├── library.db               # metadata + trạng thái từng chương
    └── <tên-truyện>/raw/        # mỗi chương một file markdown

Đứt mạng/Ctrl-C giữa chừng: chạy lại `crawl update <slug>` để tiếp tục.
Lần chạy đầu tiên tool tải index nguồn của lightnovel-crawler từ GitHub nên
cần mạng và hơi lâu; các lần sau dùng cache.

## Phát triển

    .venv/bin/pip install -e '.[dev]'
    .venv/bin/pytest

Truyện dịch tiếng Việt: giai đoạn sau — file gốc nằm ở `raw/`, bản dịch sẽ
sinh vào `vi/` cạnh đó (xem docs/superpowers/specs/).
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README with install and usage guide"
```

---

## Self-review đã thực hiện

- **Spec coverage:** 4 lệnh CLI (Task 6), bridge lncrawl (Task 4), kiến trúc adapter + registry (Task 3), SQLite schema đúng spec (Task 1), file markdown + slug Hán tự (Task 2), retry/delay/min-length/resume (Task 5), smoke test 69shuba (Task 7). Adapter native: chừa `NATIVE_ADAPTERS` + package `native/` (spec nói "trống ở giai đoạn đầu" — đúng).
- **Type consistency:** `ChapterRef(idx, title, url)` thống nhất Task 3→4→5; `download_pending(adapter, lib, library_dir, novel, ...)` thống nhất Task 5→6; `FakeAdapter` conftest dùng chung Task 5→6; cột DB (`crawl_status`, `source_url`, `idx`) khớp giữa db.py và downloader/CLI.
- **Lưu ý còn lại:** API lncrawl v4 đã xác minh bằng cài đặt thật (init_crawler/read_novel/download_chapter/list đều chạy được); rủi ro còn lại là hành vi ngoài mạng thật của từng trang — xử lý ở smoke test Task 7.
