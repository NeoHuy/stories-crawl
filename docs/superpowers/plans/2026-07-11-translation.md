# Translation (Chinese → Vietnamese) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dịch nội dung chương từ `raw/` (tiếng Trung) sang tiếng Việt vào `vi/` bằng LLM, backend cắm được (Claude hoặc endpoint OpenAI-compatible), lệnh `crawl translate` opt-in.

**Architecture:** Interface `Translator` với hai backend (`anthropic`, `openai_compat`); `registry.build_translator` chọn backend theo config/env với preset base_url. `core/translator_loop.translate_pending` mượn khuôn của `download_pending`: lấy chương `crawl_status=done` chưa dịch, gọi translator, ghi `vi/`, cập nhật DB, resume được. DB migration thêm cột trạng thái dịch.

**Tech Stack:** Python ≥ 3.10, click, `anthropic`/`openai` SDK (extra `[translate]`), SDK import lazy — test inject client giả nên không cần cài SDK/thật để chạy suite.

## Global Constraints

- Dịch là subcommand riêng `translate`; `add`/`update` KHÔNG tự dịch.
- Env là cách cấu hình chính: `STORIES_TRANSLATOR` (`claude`/`openai`/`lmstudio`/`ollama`), `STORIES_TRANSLATE_MODEL`, `STORIES_TRANSLATE_BASE_URL`, `STORIES_TRANSLATE_API_KEY`. Cờ `--provider/--model/--base-url` ghi đè tạm.
- Preset base_url: `lmstudio` → `http://localhost:1234/v1`, `ollama` → `http://localhost:11434/v1`, `openai` → mặc định SDK openai (api.openai.com); `claude`/`anthropic` → backend Anthropic (model mặc định `claude-opus-4-8`).
- Bản dịch: `library/<slug>/vi/NNNN-<tiêu đề>.md`, dòng đầu `# <tiêu đề Việt>`.
- Điều kiện dịch một chương: `crawl_status='done'`. Resume theo từng chương.
- Bản dịch rỗng hoặc `len(text_vi) < 0.3 * len(text_src)` → coi là lỗi, không ghi file.
- SDK dịch import lazy trong backend; test luôn inject client giả (không gọi mạng/LLM thật).
- Dependency dịch ở extra `[translate]`; crawler nền không đổi. Lệnh test: `.venv/bin/pytest`.
- Commit message tiếng Anh, quy ước `feat:`/`test:`/`docs:`.

**Trạng thái code hiện có (đã merge, không phá):**
- `storage/db.py`: `Library.__init__` chạy `executescript(SCHEMA)`; có `get_novel(key)`, `pending_chapters`, `mark_chapter_done/failed`, `set_novel_status`, `list_novels` (trả `done_count`, `total_count`), `_now()`.
- `storage/files.py`: `write_chapter(library_dir, slug, idx, title, text)` ghi vào `<slug>/raw/`; `sanitize`, `chapter_filename`, `_truncate_bytes`.
- `core/downloader.py`: `download_pending(...) -> DownloadSummary(done, failed, failures)`.
- `cli.py`: group `main`; `_library_dir()`; `DOWNLOAD_KWARGS`; lệnh `add`/`update`/`list`/`sources`; `list` in `f"[{id}] {title} ({slug}) — {done_count}/{total_count} chương — {status}"`.

---

## File Structure

```
stories_crawl/
├── translate/
│   ├── __init__.py       # trống
│   ├── base.py           # Translator (ABC), TranslatedChapter, TranslateError
│   ├── prompt.py         # build_system_prompt, build_user_message, parse_translation
│   ├── openai_compat.py  # OpenAICompatTranslator
│   ├── anthropic.py      # AnthropicTranslator
│   └── registry.py       # build_translator(...)
├── core/
│   └── translator_loop.py # translate_pending(...) + TranslateSummary
├── storage/
│   ├── db.py             # SỬA: migration + truy vấn dịch
│   ├── files.py          # SỬA: tham số subdir + read_chapter_body
│   └── glossary.py       # MỚI: read_glossary
└── cli.py                # SỬA: lệnh translate + cột dịch trong list
tests/
├── test_db.py            # SỬA: migration + truy vấn dịch
├── test_files.py         # SỬA: subdir + read_chapter_body
├── test_glossary.py      # MỚI
├── test_translate_prompt.py    # MỚI
├── test_translate_openai.py    # MỚI
├── test_translate_anthropic.py # MỚI
├── test_translate_registry.py  # MỚI
├── test_translator_loop.py     # MỚI
└── test_cli.py           # SỬA: lệnh translate
pyproject.toml            # SỬA: extra [translate]
README.md                 # SỬA: mục Dịch tiếng Việt
```

---

### Task 1: DB migration + truy vấn trạng thái dịch

**Files:**
- Modify: `stories_crawl/storage/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: (không có)
- Produces trên `Library`:
  - Migration tự động lúc `__init__` thêm cột vào `chapters`: `translate_status TEXT NOT NULL DEFAULT 'pending'`, `vi_path TEXT`, `translate_error TEXT`, `translated_at TEXT`, `translator TEXT`.
  - `pending_translations(novel_id, include_done=False) -> list[sqlite3.Row]`: chương `crawl_status='done'` và (`translate_status IN ('pending','failed')`, hoặc thêm `'done'` khi `include_done`), sắp theo `idx`.
  - `mark_chapter_translated(chapter_id, vi_path, translator) -> None`.
  - `mark_chapter_translate_failed(chapter_id, error) -> None`.
  - `list_novels()` trả thêm `translated_count`.

- [ ] **Step 1: Viết test (sẽ fail)**

Thêm vào `tests/test_db.py`:

```python
def test_migration_adds_translate_columns(tmp_path):
    # DB tạo bởi Library luôn có cột dịch, và mở lại vẫn idempotent
    lib = Library(tmp_path / "library.db")
    cols = {r["name"] for r in lib.conn.execute("PRAGMA table_info(chapters)")}
    assert {"translate_status", "vi_path", "translate_error",
            "translated_at", "translator"} <= cols
    lib.close()
    lib2 = Library(tmp_path / "library.db")  # mở lại không lỗi
    lib2.close()


def test_migration_on_old_db(tmp_path):
    # DB cũ (schema chưa có cột dịch) được nâng cấp, dữ liệu giữ nguyên
    import sqlite3
    p = tmp_path / "old.db"
    con = sqlite3.connect(p)
    con.executescript(
        "CREATE TABLE novels (id INTEGER PRIMARY KEY, slug TEXT UNIQUE NOT NULL,"
        " title TEXT NOT NULL, author TEXT, source_url TEXT UNIQUE NOT NULL,"
        " adapter TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,"
        " updated_at TEXT NOT NULL);"
        "CREATE TABLE chapters (id INTEGER PRIMARY KEY, novel_id INTEGER NOT NULL,"
        " idx INTEGER NOT NULL, title TEXT, source_url TEXT NOT NULL, file_path TEXT,"
        " crawl_status TEXT NOT NULL, error TEXT, updated_at TEXT NOT NULL,"
        " UNIQUE(novel_id, idx));"
        "INSERT INTO chapters (novel_id, idx, source_url, crawl_status, updated_at)"
        " VALUES (1, 1, 'u', 'done', 't');"
    )
    con.commit(); con.close()
    lib = Library(p)
    row = lib.conn.execute("SELECT translate_status FROM chapters WHERE idx=1").fetchone()
    assert row["translate_status"] == "pending"  # default áp cho hàng cũ
    lib.close()


def test_pending_translations(lib):
    novel_id = _add_novel(lib)
    lib.add_chapters(novel_id, [Ref(1, "第一章", "u1"), Ref(2, "第二章", "u2"),
                                Ref(3, "第三章", "u3")])
    # chương 1,2 đã crawl xong; 3 vẫn pending crawl
    c1 = _chapter(lib, novel_id, 1)["id"]
    c2 = _chapter(lib, novel_id, 2)["id"]
    lib.mark_chapter_done(c1, "s/raw/0001.md")
    lib.mark_chapter_done(c2, "s/raw/0002.md")
    # chỉ chương đã done mới nằm trong hàng chờ dịch
    assert [r["idx"] for r in lib.pending_translations(novel_id)] == [1, 2]
    # dịch xong chương 1
    lib.mark_chapter_translated(c1, "s/vi/0001.md", "fake-model")
    assert [r["idx"] for r in lib.pending_translations(novel_id)] == [2]
    # include_done lấy lại cả chương đã dịch
    assert [r["idx"] for r in lib.pending_translations(novel_id, include_done=True)] == [1, 2]
    # dịch lỗi chương 2 → vẫn nằm chờ (retry)
    lib.mark_chapter_translate_failed(c2, "boom")
    assert [r["idx"] for r in lib.pending_translations(novel_id)] == [2]
    assert _chapter(lib, novel_id, 2)["translate_error"] == "boom"


def test_list_novels_translated_count(lib):
    novel_id = _add_novel(lib)
    lib.add_chapters(novel_id, [Ref(1, "t1", "u1"), Ref(2, "t2", "u2")])
    c1 = _chapter(lib, novel_id, 1)["id"]
    lib.mark_chapter_done(c1, "s/raw/0001.md")
    lib.mark_chapter_translated(c1, "s/vi/0001.md", "m")
    row = lib.list_novels()[0]
    assert row["translated_count"] == 1
    assert row["total_count"] == 2
```

(`_chapter` helper đã có sẵn trong test_db.py từ đợt hardening.)

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `.venv/bin/pytest tests/test_db.py -k "migration or pending_translations or translated_count" -v`
Expected: FAIL (`no such column: translate_status` / `AttributeError`).

- [ ] **Step 3: Sửa `stories_crawl/storage/db.py`**

Thêm hằng số migration sau `SCHEMA` (trước `def _now`):

```python
_TRANSLATE_COLUMNS = {
    "translate_status": "TEXT NOT NULL DEFAULT 'pending'",
    "vi_path": "TEXT",
    "translate_error": "TEXT",
    "translated_at": "TEXT",
    "translator": "TEXT",
}
```

Trong `__init__`, sau khối `executescript(SCHEMA)`, gọi migration:

```python
        with self.conn:
            self.conn.executescript(SCHEMA)
        self._migrate()
```

Thêm các method vào `Library`:

```python
    def _migrate(self):
        existing = {
            r["name"] for r in self.conn.execute("PRAGMA table_info(chapters)")
        }
        with self.conn:
            for col, decl in _TRANSLATE_COLUMNS.items():
                if col not in existing:
                    self.conn.execute(
                        f"ALTER TABLE chapters ADD COLUMN {col} {decl}"
                    )

    def pending_translations(self, novel_id, include_done=False):
        statuses = ["pending", "failed"]
        if include_done:
            statuses.append("done")
        placeholders = ", ".join("?" for _ in statuses)
        return self.conn.execute(
            "SELECT * FROM chapters"
            " WHERE novel_id = ? AND crawl_status = 'done'"
            f" AND translate_status IN ({placeholders})"
            " ORDER BY idx",
            (novel_id, *statuses),
        ).fetchall()

    def mark_chapter_translated(self, chapter_id, vi_path, translator):
        with self.conn:
            self.conn.execute(
                "UPDATE chapters SET translate_status = 'done', vi_path = ?,"
                " translator = ?, translate_error = NULL, translated_at = ?"
                " WHERE id = ?",
                (vi_path, translator, _now(), chapter_id),
            )

    def mark_chapter_translate_failed(self, chapter_id, error):
        with self.conn:
            self.conn.execute(
                "UPDATE chapters SET translate_status = 'failed',"
                " translate_error = ?, translated_at = ? WHERE id = ?",
                (error, _now(), chapter_id),
            )
```

Trong `list_novels`, thêm `translated_count` vào SELECT:

```python
    def list_novels(self):
        return self.conn.execute(
            "SELECT n.*,"
            " COUNT(c.id) AS total_count,"
            " COALESCE(SUM(CASE WHEN c.crawl_status = 'done' THEN 1 ELSE 0 END), 0)"
            "   AS done_count,"
            " COALESCE(SUM(CASE WHEN c.translate_status = 'done' THEN 1 ELSE 0 END), 0)"
            "   AS translated_count"
            " FROM novels n LEFT JOIN chapters c ON c.novel_id = n.id"
            " GROUP BY n.id ORDER BY n.updated_at DESC"
        ).fetchall()
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `.venv/bin/pytest tests/test_db.py -v`
Expected: tất cả pass (bộ cũ + 4 test mới).

- [ ] **Step 5: Commit**

```bash
git add stories_crawl/storage/db.py tests/test_db.py
git commit -m "feat: add chapter translation state (migration + queries)"
```

---

### Task 2: `files.py` subdir + read_chapter_body; `glossary.py`

**Files:**
- Modify: `stories_crawl/storage/files.py`
- Create: `stories_crawl/storage/glossary.py`
- Test: `tests/test_files.py`, `tests/test_glossary.py`

**Interfaces:**
- Consumes: (không có)
- Produces:
  - `write_chapter(library_dir, slug, idx, title, text, subdir="raw") -> str` — thêm tham số `subdir`; mặc định `"raw"` (giữ nguyên hành vi cũ).
  - `read_chapter_body(library_dir, rel_path) -> str` — đọc file markdown, bỏ dòng tiêu đề `# ...` và dòng trống ngay sau, trả phần thân.
  - `read_glossary(library_dir, slug) -> str | None` trong `storage/glossary.py`.

- [ ] **Step 1: Viết test (sẽ fail)**

Thêm vào `tests/test_files.py`:

```python
def test_write_chapter_subdir(tmp_path):
    from stories_crawl.storage.files import write_chapter, read_chapter_body
    rel = write_chapter(tmp_path, "s", 1, "Nhan đề", "thân bài", subdir="vi")
    assert rel == "s/vi/0001-Nhan-đề.md"
    assert (tmp_path / "s" / "vi").is_dir()


def test_read_chapter_body(tmp_path):
    from stories_crawl.storage.files import write_chapter, read_chapter_body
    rel = write_chapter(tmp_path, "s", 1, "第一章", "内容dòng1\n内容dòng2")
    body = read_chapter_body(tmp_path, rel)
    assert body == "内容dòng1\n内容dòng2"  # đã bỏ "# 第一章" và dòng trống


def test_read_chapter_body_no_heading(tmp_path):
    from stories_crawl.storage.files import read_chapter_body
    p = tmp_path / "s" / "raw"
    p.mkdir(parents=True)
    (p / "x.md").write_text("chỉ có nội dung\nkhông heading\n", encoding="utf-8")
    assert read_chapter_body(tmp_path, "s/raw/x.md") == "chỉ có nội dung\nkhông heading"
```

`tests/test_glossary.py`:

```python
from stories_crawl.storage.glossary import read_glossary


def test_read_glossary_missing(tmp_path):
    assert read_glossary(tmp_path, "s") is None


def test_read_glossary_parses(tmp_path):
    d = tmp_path / "s"
    d.mkdir()
    (d / "glossary.md").write_text(
        "# ghi chú (bỏ qua)\n\n炎少 = Viêm thiếu\n斗气 = Đấu khí\n",
        encoding="utf-8",
    )
    g = read_glossary(tmp_path, "s")
    assert "炎少 = Viêm thiếu" in g
    assert "斗气 = Đấu khí" in g
    assert "ghi chú" not in g  # dòng '#' và dòng trống bị loại


def test_read_glossary_empty_returns_none(tmp_path):
    d = tmp_path / "s"
    d.mkdir()
    (d / "glossary.md").write_text("# chỉ có comment\n\n", encoding="utf-8")
    assert read_glossary(tmp_path, "s") is None
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `.venv/bin/pytest tests/test_files.py -k "subdir or read_chapter_body" tests/test_glossary.py -v`
Expected: FAIL (`TypeError` subdir / `ImportError` glossary).

- [ ] **Step 3: Sửa `files.py`, viết `glossary.py`**

Trong `stories_crawl/storage/files.py`, đổi `write_chapter` và thêm `read_chapter_body`:

```python
def write_chapter(library_dir: Path, slug: str, idx: int, title: str, text: str,
                  subdir: str = "raw") -> str:
    rel = Path(slug) / subdir / chapter_filename(idx, title)
    path = library_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"# {title}\n\n{text}\n" if title else f"{text}\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
    return rel.as_posix()


def read_chapter_body(library_dir: Path, rel_path: str) -> str:
    content = (Path(library_dir) / rel_path).read_text(encoding="utf-8")
    lines = content.split("\n")
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
        if lines and lines[0] == "":
            lines = lines[1:]
    return "\n".join(lines).rstrip("\n")
```

`stories_crawl/storage/glossary.py`:

```python
from pathlib import Path


def read_glossary(library_dir, slug: str) -> str | None:
    path = Path(library_dir) / slug / "glossary.md"
    if not path.exists():
        return None
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        lines.append(s)
    return "\n".join(lines) if lines else None
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `.venv/bin/pytest tests/test_files.py tests/test_glossary.py -v`
Expected: pass hết.

- [ ] **Step 5: Commit**

```bash
git add stories_crawl/storage/files.py stories_crawl/storage/glossary.py tests/test_files.py tests/test_glossary.py
git commit -m "feat: vi/ subdir writes, raw body reader, glossary loader"
```

---

### Task 3: `translate/base.py` + `translate/prompt.py`

**Files:**
- Create: `stories_crawl/translate/__init__.py`, `stories_crawl/translate/base.py`, `stories_crawl/translate/prompt.py`
- Test: `tests/test_translate_prompt.py`

**Interfaces:**
- Consumes: (không có)
- Produces:
  - `base.py`: `class TranslateError(Exception)`; `@dataclass TranslatedChapter(title: str, text: str)`; `class Translator(ABC)` với `translate_chapter(self, title, text, glossary=None) -> TranslatedChapter` (trừu tượng) và `close(self) -> None` (no-op).
  - `prompt.py`: `build_system_prompt(glossary: str | None = None) -> str`; `build_user_message(title: str, text: str) -> str`; `parse_translation(output: str, fallback_title: str) -> tuple[str, str]` (bóc dòng `NHAN ĐỀ:` nếu có, không thì trả `(fallback_title, output)`).

- [ ] **Step 1: Viết test (sẽ fail)**

`tests/test_translate_prompt.py`:

```python
from stories_crawl.translate.prompt import (
    build_system_prompt,
    build_user_message,
    parse_translation,
)


def test_system_prompt_without_glossary():
    p = build_system_prompt()
    assert "tiếng Việt" in p
    assert "NHAN ĐỀ" in p  # có hướng dẫn định dạng đầu ra


def test_system_prompt_with_glossary():
    p = build_system_prompt("炎少 = Viêm thiếu")
    assert "炎少 = Viêm thiếu" in p


def test_user_message():
    m = build_user_message("第一章", "nội dung")
    assert "第一章" in m and "nội dung" in m


def test_parse_translation_with_marker():
    out = "NHAN ĐỀ: Chương 1\n\nĐây là nội dung đã dịch."
    title, text = parse_translation(out, "第一章")
    assert title == "Chương 1"
    assert text == "Đây là nội dung đã dịch."


def test_parse_translation_without_marker():
    out = "Chỉ có nội dung, không có nhãn."
    title, text = parse_translation(out, "第一章")
    assert title == "第一章"  # dùng fallback
    assert text == "Chỉ có nội dung, không có nhãn."
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `.venv/bin/pytest tests/test_translate_prompt.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Viết base.py, prompt.py**

`stories_crawl/translate/base.py`:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass


class TranslateError(Exception):
    pass


@dataclass
class TranslatedChapter:
    title: str
    text: str


class Translator(ABC):
    @abstractmethod
    def translate_chapter(self, title: str, text: str,
                          glossary: str | None = None) -> TranslatedChapter: ...

    def close(self) -> None:
        pass
```

`stories_crawl/translate/prompt.py`:

```python
_SYSTEM_BASE = (
    "Bạn là dịch giả chuyên nghiệp, dịch tiểu thuyết mạng từ tiếng Trung sang "
    "tiếng Việt. Giữ nguyên văn phong, giọng điệu và ý nghĩa; không thêm, bớt "
    "hay tóm tắt nội dung; giữ cách chia đoạn. Dịch cả nhan đề chương.\n"
    "Trả về ĐÚNG định dạng: dòng đầu là `NHAN ĐỀ: <nhan đề tiếng Việt>`, "
    "một dòng trống, rồi phần nội dung đã dịch. Chỉ trả bản dịch, không kèm "
    "lời giải thích."
)


def build_system_prompt(glossary: str | None = None) -> str:
    if glossary:
        return (
            _SYSTEM_BASE
            + "\n\nDùng đúng cách dịch tên riêng/thuật ngữ trong bảng sau "
            "(định dạng `Hán = Việt`):\n" + glossary
        )
    return _SYSTEM_BASE


def build_user_message(title: str, text: str) -> str:
    return f"Nhan đề: {title}\n\n{text}"


def parse_translation(output: str, fallback_title: str) -> tuple:
    stripped = output.strip()
    lines = stripped.split("\n")
    if lines and lines[0].strip().upper().startswith("NHAN ĐỀ:"):
        title = lines[0].split(":", 1)[1].strip()
        text = "\n".join(lines[1:]).strip()
        return (title or fallback_title, text)
    return (fallback_title, stripped)
```

`stories_crawl/translate/__init__.py`: file trống.

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `.venv/bin/pytest tests/test_translate_prompt.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add stories_crawl/translate/__init__.py stories_crawl/translate/base.py stories_crawl/translate/prompt.py tests/test_translate_prompt.py
git commit -m "feat: translator interface and prompt/parse helpers"
```

---

### Task 4: `translate/openai_compat.py`

**Files:**
- Create: `stories_crawl/translate/openai_compat.py`
- Test: `tests/test_translate_openai.py`

**Interfaces:**
- Consumes: `Translator`, `TranslatedChapter`, `TranslateError` (Task 3); `build_system_prompt`, `build_user_message`, `parse_translation` (Task 3).
- Produces: `OpenAICompatTranslator(model, base_url=None, api_key="not-needed", *, client=None, max_tokens=4096)` — nếu `client=None` thì lazy import `openai` và tạo `OpenAI(base_url=..., api_key=...)`; test inject `client`. `.model` là thuộc tính công khai (loop dùng làm tên translator).

- [ ] **Step 1: Viết test (sẽ fail)**

`tests/test_translate_openai.py`:

```python
from types import SimpleNamespace

import pytest

from stories_crawl.translate.base import TranslateError
from stories_crawl.translate.openai_compat import OpenAICompatTranslator


class FakeChat:
    def __init__(self, content=None, error=None):
        self._content = content
        self._error = error
        self.calls = []

    class _Completions:
        def __init__(self, outer):
            self.outer = outer

        def create(self, **kwargs):
            self.outer.calls.append(kwargs)
            if self.outer._error:
                raise self.outer._error
            msg = SimpleNamespace(content=self.outer._content)
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    @property
    def completions(self):
        return FakeChat._Completions(self)


class FakeClient:
    def __init__(self, content=None, error=None):
        self.chat = FakeChat(content=content, error=error)


def test_translate_ok():
    client = FakeClient(content="NHAN ĐỀ: Chương 1\n\nNội dung dịch dài.")
    t = OpenAICompatTranslator(model="qwen", base_url="http://x/v1", client=client)
    out = t.translate_chapter("第一章", "原文", glossary="炎少 = Viêm thiếu")
    assert out.title == "Chương 1"
    assert "Nội dung dịch" in out.text
    # gửi đúng model + có system chứa glossary
    kw = client.chat.calls[0]
    assert kw["model"] == "qwen"
    assert any("炎少" in m["content"] for m in kw["messages"] if m["role"] == "system")


def test_translate_empty_raises():
    t = OpenAICompatTranslator(model="m", base_url="http://x/v1",
                               client=FakeClient(content="   "))
    with pytest.raises(TranslateError):
        t.translate_chapter("t", "x")


def test_translate_network_error_wrapped():
    t = OpenAICompatTranslator(model="m", base_url="http://x/v1",
                               client=FakeClient(error=ConnectionError("down")))
    with pytest.raises(TranslateError):
        t.translate_chapter("t", "x")
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `.venv/bin/pytest tests/test_translate_openai.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Viết `openai_compat.py`**

```python
from .base import TranslateError, TranslatedChapter, Translator
from .prompt import build_system_prompt, build_user_message, parse_translation


class OpenAICompatTranslator(Translator):
    def __init__(self, model, base_url=None, api_key="not-needed", *,
                 client=None, max_tokens=4096):
        self.model = model
        self.max_tokens = max_tokens
        if client is not None:
            self._client = client
        else:
            try:
                from openai import OpenAI
            except ImportError as e:
                raise TranslateError(
                    "Chưa cài SDK openai — chạy: pip install -e '.[translate]'"
                ) from e
            self._client = OpenAI(base_url=base_url, api_key=api_key)

    def translate_chapter(self, title, text, glossary=None):
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": build_system_prompt(glossary)},
                    {"role": "user", "content": build_user_message(title, text)},
                ],
            )
        except Exception as e:
            raise TranslateError(f"Lỗi gọi backend dịch: {e}") from e
        out = (resp.choices[0].message.content or "").strip()
        if not out:
            raise TranslateError("Backend dịch trả về rỗng")
        vi_title, vi_text = parse_translation(out, title)
        return TranslatedChapter(title=vi_title, text=vi_text)
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `.venv/bin/pytest tests/test_translate_openai.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add stories_crawl/translate/openai_compat.py tests/test_translate_openai.py
git commit -m "feat: OpenAI-compatible translator backend (LM Studio/Ollama/OpenAI)"
```

---

### Task 5: `translate/anthropic.py`

**Files:**
- Create: `stories_crawl/translate/anthropic.py`
- Test: `tests/test_translate_anthropic.py`

**Interfaces:**
- Consumes: `Translator`, `TranslatedChapter`, `TranslateError`, prompt helpers (Task 3).
- Produces: `AnthropicTranslator(model, api_key=None, *, client=None, max_tokens=8000)` — nếu `client=None` thì lazy import `anthropic` và tạo client; test inject `client`. `.model` công khai. Đọc kết quả từ `resp.content` (các block `type=="text"`).

- [ ] **Step 1: Viết test (sẽ fail)**

`tests/test_translate_anthropic.py`:

```python
from types import SimpleNamespace

import pytest

from stories_crawl.translate.anthropic import AnthropicTranslator
from stories_crawl.translate.base import TranslateError


class FakeMessages:
    def __init__(self, blocks=None, error=None):
        self._blocks = blocks or []
        self._error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return SimpleNamespace(content=self._blocks)


class FakeClient:
    def __init__(self, blocks=None, error=None):
        self.messages = FakeMessages(blocks=blocks, error=error)


def _text_block(t):
    return SimpleNamespace(type="text", text=t)


def test_translate_ok():
    client = FakeClient(blocks=[_text_block("NHAN ĐỀ: Chương 1\n\nBản dịch dài.")])
    t = AnthropicTranslator(model="claude-opus-4-8", client=client)
    out = t.translate_chapter("第一章", "原文")
    assert out.title == "Chương 1"
    assert "Bản dịch" in out.text
    assert client.messages.calls[0]["model"] == "claude-opus-4-8"
    # dùng system (không phải role system trong messages)
    assert "tiếng Việt" in client.messages.calls[0]["system"]


def test_translate_empty_raises():
    t = AnthropicTranslator(model="m", client=FakeClient(blocks=[_text_block("  ")]))
    with pytest.raises(TranslateError):
        t.translate_chapter("t", "x")


def test_translate_error_wrapped():
    t = AnthropicTranslator(model="m", client=FakeClient(error=RuntimeError("boom")))
    with pytest.raises(TranslateError):
        t.translate_chapter("t", "x")
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `.venv/bin/pytest tests/test_translate_anthropic.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Viết `anthropic.py`**

```python
from .base import TranslateError, TranslatedChapter, Translator
from .prompt import build_system_prompt, build_user_message, parse_translation


class AnthropicTranslator(Translator):
    def __init__(self, model, api_key=None, *, client=None, max_tokens=8000):
        self.model = model
        self.max_tokens = max_tokens
        if client is not None:
            self._client = client
        else:
            try:
                import anthropic
            except ImportError as e:
                raise TranslateError(
                    "Chưa cài SDK anthropic — chạy: pip install -e '.[translate]'"
                ) from e
            self._client = (
                anthropic.Anthropic(api_key=api_key) if api_key
                else anthropic.Anthropic()
            )

    def translate_chapter(self, title, text, glossary=None):
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=build_system_prompt(glossary),
                messages=[
                    {"role": "user", "content": build_user_message(title, text)}
                ],
            )
        except Exception as e:
            raise TranslateError(f"Lỗi gọi Claude: {e}") from e
        parts = [
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        ]
        out = "".join(parts).strip()
        if not out:
            raise TranslateError("Claude trả về rỗng")
        vi_title, vi_text = parse_translation(out, title)
        return TranslatedChapter(title=vi_title, text=vi_text)
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `.venv/bin/pytest tests/test_translate_anthropic.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add stories_crawl/translate/anthropic.py tests/test_translate_anthropic.py
git commit -m "feat: Anthropic (Claude) translator backend"
```

---

### Task 6: `translate/registry.py`

**Files:**
- Create: `stories_crawl/translate/registry.py`
- Test: `tests/test_translate_registry.py`

**Interfaces:**
- Consumes: `TranslateError` (Task 3); `AnthropicTranslator` (Task 5), `OpenAICompatTranslator` (Task 4) — import bên trong hàm để test monkeypatch được.
- Produces: `build_translator(provider=None, model=None, base_url=None, api_key=None) -> Translator`; đọc mặc định từ env `STORIES_TRANSLATOR/STORIES_TRANSLATE_MODEL/STORIES_TRANSLATE_BASE_URL/STORIES_TRANSLATE_API_KEY`; preset base_url; lỗi rõ ràng khi thiếu.

- [ ] **Step 1: Viết test (sẽ fail)**

`tests/test_translate_registry.py`:

```python
import pytest

from stories_crawl.translate import registry
from stories_crawl.translate.base import TranslateError


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    for k in ("STORIES_TRANSLATOR", "STORIES_TRANSLATE_MODEL",
              "STORIES_TRANSLATE_BASE_URL", "STORIES_TRANSLATE_API_KEY"):
        monkeypatch.delenv(k, raising=False)


def test_missing_provider_raises():
    with pytest.raises(TranslateError, match="provider"):
        registry.build_translator()


def test_claude_routes_to_anthropic(monkeypatch):
    captured = {}

    class FakeAnthropic:
        def __init__(self, model, api_key=None):
            captured["model"] = model
            captured["api_key"] = api_key

    monkeypatch.setattr(
        "stories_crawl.translate.anthropic.AnthropicTranslator", FakeAnthropic
    )
    registry.build_translator(provider="claude", api_key="sk-x")
    assert captured["model"] == "claude-opus-4-8"  # mặc định
    assert captured["api_key"] == "sk-x"


def test_ollama_preset_base_url(monkeypatch):
    captured = {}

    class FakeOpenAI:
        def __init__(self, model, base_url=None, api_key="not-needed"):
            captured["model"] = model
            captured["base_url"] = base_url

    monkeypatch.setattr(
        "stories_crawl.translate.openai_compat.OpenAICompatTranslator", FakeOpenAI
    )
    registry.build_translator(provider="ollama", model="qwen2.5")
    assert captured["base_url"] == "http://localhost:11434/v1"
    assert captured["model"] == "qwen2.5"


def test_openai_default_base_url_none(monkeypatch):
    captured = {}

    class FakeOpenAI:
        def __init__(self, model, base_url=None, api_key="not-needed"):
            captured["base_url"] = base_url

    monkeypatch.setattr(
        "stories_crawl.translate.openai_compat.OpenAICompatTranslator", FakeOpenAI
    )
    registry.build_translator(provider="openai", model="gpt-4o", api_key="sk")
    assert captured["base_url"] is None  # dùng mặc định SDK openai (OpenAI thật)


def test_openai_missing_model_raises():
    with pytest.raises(TranslateError, match="model"):
        registry.build_translator(provider="lmstudio")


def test_unknown_provider_raises():
    with pytest.raises(TranslateError, match="không hỗ trợ"):
        registry.build_translator(provider="bogus", model="m")


def test_env_defaults(monkeypatch):
    monkeypatch.setenv("STORIES_TRANSLATOR", "ollama")
    monkeypatch.setenv("STORIES_TRANSLATE_MODEL", "llama3.1")
    captured = {}

    class FakeOpenAI:
        def __init__(self, model, base_url=None, api_key="not-needed"):
            captured["model"] = model

    monkeypatch.setattr(
        "stories_crawl.translate.openai_compat.OpenAICompatTranslator", FakeOpenAI
    )
    registry.build_translator()  # không tham số → đọc env
    assert captured["model"] == "llama3.1"
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `.venv/bin/pytest tests/test_translate_registry.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Viết `registry.py`**

```python
import os

from .base import TranslateError

_OPENAI_PRESETS = {
    "lmstudio": "http://localhost:1234/v1",
    "ollama": "http://localhost:11434/v1",
    "openai": None,  # None → SDK openai dùng mặc định api.openai.com (OpenAI thật)
}


def build_translator(provider=None, model=None, base_url=None, api_key=None):
    provider = provider or os.environ.get("STORIES_TRANSLATOR")
    model = model or os.environ.get("STORIES_TRANSLATE_MODEL")
    base_url = base_url or os.environ.get("STORIES_TRANSLATE_BASE_URL")
    api_key = api_key or os.environ.get("STORIES_TRANSLATE_API_KEY")

    if not provider:
        raise TranslateError(
            "Chưa cấu hình provider dịch (đặt STORIES_TRANSLATOR hoặc dùng --provider)"
        )

    if provider in ("claude", "anthropic"):
        from .anthropic import AnthropicTranslator

        return AnthropicTranslator(
            model=model or "claude-opus-4-8", api_key=api_key
        )

    if provider in _OPENAI_PRESETS:
        from .openai_compat import OpenAICompatTranslator

        if not model:
            raise TranslateError(
                "Thiếu model dịch (đặt STORIES_TRANSLATE_MODEL hoặc dùng --model)"
            )
        resolved = base_url or _OPENAI_PRESETS[provider]
        return OpenAICompatTranslator(
            model=model, base_url=resolved, api_key=api_key or "not-needed"
        )

    raise TranslateError(f"Provider dịch không hỗ trợ: {provider}")
```

- [ ] **Step 4: Chạy test, xác nhận pass**

Run: `.venv/bin/pytest tests/test_translate_registry.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add stories_crawl/translate/registry.py tests/test_translate_registry.py
git commit -m "feat: translator registry with provider presets"
```

---

### Task 7: `core/translator_loop.py`

**Files:**
- Create: `stories_crawl/core/translator_loop.py`
- Modify: `tests/conftest.py` (thêm `FakeTranslator`)
- Test: `tests/test_translator_loop.py`

**Interfaces:**
- Consumes: `Library.pending_translations/mark_chapter_translated/mark_chapter_translate_failed` (Task 1); `write_chapter(..., subdir="vi")`, `read_chapter_body` (Task 2); `Translator`/`TranslatedChapter`/`TranslateError` (Task 3).
- Produces:
  - `@dataclass TranslateSummary(done=0, failed=0, failures=[])` (failures là tuple `(idx, title, err)`).
  - `translate_pending(translator, lib, library_dir, novel, glossary=None, *, limit=None, include_done=False, min_ratio=0.3, max_retries=3, sleep=time.sleep, log=print) -> TranslateSummary`.
  - `tests/conftest.py`: `class FakeTranslator(Translator)` — dịch bằng cách thêm tiền tố `[VI] `; `fail_idxs`/`empty_idxs` để mô phỏng lỗi; `.model = "fake-model"`.

- [ ] **Step 1: Thêm `FakeTranslator` vào `tests/conftest.py`**

```python
from stories_crawl.translate.base import TranslatedChapter, Translator


class FakeTranslator(Translator):
    """Translator giả cho test: dịch = thêm tiền tố, có thể giả lập lỗi/rỗng."""

    model = "fake-model"

    def __init__(self, fail_bodies=(), empty_bodies=()):
        self.fail_bodies = set(fail_bodies)   # body nào thì ném lỗi
        self.empty_bodies = set(empty_bodies) # body nào thì trả rỗng
        self.calls = []
        self.closed = False

    def translate_chapter(self, title, text, glossary=None):
        self.calls.append((title, text, glossary))
        if text in self.fail_bodies:
            raise RuntimeError("mô phỏng lỗi dịch")
        if text in self.empty_bodies:
            return TranslatedChapter(title=f"[VI] {title}", text="")
        return TranslatedChapter(title=f"[VI] {title}", text=f"[VI] {text}")

    def close(self):
        self.closed = True
```

- [ ] **Step 2: Viết test (sẽ fail)**

`tests/test_translator_loop.py`:

```python
import pytest

from stories_crawl.core.translator_loop import translate_pending
from stories_crawl.storage.db import Library
from stories_crawl.storage.files import write_chapter

from conftest import FakeTranslator


def _no_sleep(_):
    pass


@pytest.fixture
def env(tmp_path):
    lib = Library(tmp_path / "library.db")
    novel_id = lib.create_novel("truyen", "Truyện", "TG",
                                "https://x.com/b", "fake")

    class Ref:
        def __init__(self, idx, title, url):
            self.idx = idx
            self.title = title
            self.url = url

    lib.add_chapters(novel_id, [Ref(1, "第一章", "u1"), Ref(2, "第二章", "u2")])
    # crawl xong 2 chương: ghi raw + đánh dấu done
    for idx, title, body in [(1, "第一章", "正文一" * 50), (2, "第二章", "正文二" * 50)]:
        rel = write_chapter(tmp_path, "truyen", idx, title, body)
        ch = next(r for r in lib.pending_chapters(novel_id) if r["idx"] == idx)
        lib.mark_chapter_done(ch["id"], rel)
    novel = lib.get_novel(str(novel_id))
    yield tmp_path, lib, novel
    lib.close()


def test_translates_all_pending(env):
    tmp_path, lib, novel = env
    t = FakeTranslator()
    summary = translate_pending(t, lib, tmp_path, novel, sleep=_no_sleep,
                                log=lambda *_: None)
    assert (summary.done, summary.failed) == (2, 0)
    assert lib.pending_translations(novel["id"]) == []
    f = tmp_path / "truyen" / "vi" / "0001-[VI]-第一章.md"
    assert f.read_text(encoding="utf-8").startswith("# [VI] 第一章")


def test_limit(env):
    tmp_path, lib, novel = env
    summary = translate_pending(FakeTranslator(), lib, tmp_path, novel, limit=1,
                                sleep=_no_sleep, log=lambda *_: None)
    assert summary.done == 1
    assert len(lib.pending_translations(novel["id"])) == 1


def test_failure_marks_failed(env):
    tmp_path, lib, novel = env
    t = FakeTranslator(fail_bodies={"正文一" * 50})
    summary = translate_pending(t, lib, tmp_path, novel, sleep=_no_sleep,
                                log=lambda *_: None)
    assert (summary.done, summary.failed) == (1, 1)
    assert [r["idx"] for r in lib.pending_translations(novel["id"])] == [1]


def test_empty_translation_marks_failed(env):
    tmp_path, lib, novel = env
    t = FakeTranslator(empty_bodies={"正文一" * 50})
    summary = translate_pending(t, lib, tmp_path, novel, sleep=_no_sleep,
                                log=lambda *_: None)
    assert summary.failed == 1
    assert not (tmp_path / "truyen" / "vi" / "0001-[VI]-第一章.md").exists()


def test_resume_skips_done(env):
    tmp_path, lib, novel = env
    translate_pending(FakeTranslator(), lib, tmp_path, novel, sleep=_no_sleep,
                      log=lambda *_: None)
    t2 = FakeTranslator()
    summary = translate_pending(t2, lib, tmp_path, novel, sleep=_no_sleep,
                                log=lambda *_: None)
    assert (summary.done, summary.failed) == (0, 0)
    assert t2.calls == []


def test_retranslate_includes_done(env):
    tmp_path, lib, novel = env
    translate_pending(FakeTranslator(), lib, tmp_path, novel, sleep=_no_sleep,
                      log=lambda *_: None)
    t2 = FakeTranslator()
    summary = translate_pending(t2, lib, tmp_path, novel, include_done=True,
                                sleep=_no_sleep, log=lambda *_: None)
    assert summary.done == 2  # dịch lại cả 2
```

- [ ] **Step 3: Chạy test, xác nhận fail**

Run: `.venv/bin/pytest tests/test_translator_loop.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 4: Viết `core/translator_loop.py`**

```python
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..storage.files import read_chapter_body, write_chapter


@dataclass
class TranslateSummary:
    done: int = 0
    failed: int = 0
    failures: list = field(default_factory=list)


def translate_pending(translator, lib, library_dir: Path, novel, glossary=None, *,
                      limit=None, include_done=False, min_ratio=0.3,
                      max_retries=3, sleep=time.sleep, log=print) -> TranslateSummary:
    summary = TranslateSummary()
    chapters = lib.pending_translations(novel["id"], include_done=include_done)
    if limit is not None:
        chapters = chapters[:limit]
    model_name = getattr(translator, "model", "unknown")
    for i, ch in enumerate(chapters):
        src = read_chapter_body(library_dir, ch["file_path"])
        last_error = ""
        for attempt in range(1, max_retries + 1):
            try:
                result = translator.translate_chapter(
                    ch["title"] or "", src, glossary
                )
                if not result.text or len(result.text) < min_ratio * len(src):
                    raise ValueError("Bản dịch rỗng hoặc quá ngắn so với bản gốc")
                rel = write_chapter(
                    library_dir, novel["slug"], ch["idx"],
                    result.title, result.text, subdir="vi",
                )
                lib.mark_chapter_translated(ch["id"], rel, model_name)
                summary.done += 1
                log(f"  [{ch['idx']:>5}] {ch['title']} — dịch OK")
                break
            except Exception as e:
                last_error = str(e) or type(e).__name__
                if attempt < max_retries:
                    sleep(2 ** (attempt - 1))
        else:
            lib.mark_chapter_translate_failed(ch["id"], last_error)
            summary.failed += 1
            summary.failures.append((ch["idx"], ch["title"] or "", last_error))
            log(f"  [{ch['idx']:>5}] {ch['title']} — LỖI: {last_error}")
    return summary
```

- [ ] **Step 5: Chạy test, xác nhận pass**

Run: `.venv/bin/pytest tests/test_translator_loop.py -v`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add stories_crawl/core/translator_loop.py tests/conftest.py tests/test_translator_loop.py
git commit -m "feat: chapter translation loop with retry and resume"
```

---

### Task 8: CLI `translate` + cột dịch trong `list`; extra + README + smoke test

**Files:**
- Modify: `stories_crawl/cli.py`, `pyproject.toml`, `README.md`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `build_translator` (Task 6), `translate_pending` (Task 7), `read_glossary` (Task 2), `TranslateError` (Task 3), `Library.get_novel/list_novels` (có sẵn).
- Produces: lệnh `crawl translate <key>` với cờ `--provider/--model/--base-url/--limit/--retranslate`; `list` in thêm `dịch X/Y`; `TRANSLATE_KWARGS` (test tắt sleep).

- [ ] **Step 1: Viết test (sẽ fail)**

Thêm vào `tests/test_cli.py`:

```python
from conftest import FakeTranslator


@pytest.fixture
def trans_runner(tmp_path, monkeypatch):
    monkeypatch.setenv("STORIES_LIBRARY", str(tmp_path / "library"))
    monkeypatch.setattr(registry, "NATIVE_ADAPTERS", [FakeAdapter])
    monkeypatch.setattr("stories_crawl.cli.DOWNLOAD_KWARGS", {"sleep": lambda _: None})
    monkeypatch.setattr("stories_crawl.cli.TRANSLATE_KWARGS", {"sleep": lambda _: None})
    return CliRunner(), tmp_path / "library"


def test_translate_command(trans_runner, monkeypatch):
    cli, lib_dir = trans_runner
    cli.invoke(main, ["add", "https://fake-site.com/book/1"])  # crawl trước
    monkeypatch.setattr(
        "stories_crawl.cli.build_translator", lambda **kw: FakeTranslator()
    )
    result = cli.invoke(main, ["translate", "Truyện-Giả"])
    assert result.exit_code == 0, result.output
    assert "Dịch xong: 2 OK" in result.output
    assert (lib_dir / "Truyện-Giả" / "vi" / "0001-[VI]-Chương-1.md").exists()


def test_translate_unknown_novel(trans_runner):
    cli, _ = trans_runner
    result = cli.invoke(main, ["translate", "không-có"])
    assert result.exit_code != 0
    assert "Không tìm thấy" in result.output


def test_translate_config_error(trans_runner, monkeypatch):
    cli, _ = trans_runner
    cli.invoke(main, ["add", "https://fake-site.com/book/1"])
    from stories_crawl.translate.base import TranslateError

    def _boom(**kw):
        raise TranslateError("Chưa cấu hình provider dịch")

    monkeypatch.setattr("stories_crawl.cli.build_translator", _boom)
    result = cli.invoke(main, ["translate", "Truyện-Giả"])
    assert result.exit_code != 0
    assert "provider" in result.output


def test_list_shows_translation_progress(trans_runner, monkeypatch):
    cli, _ = trans_runner
    cli.invoke(main, ["add", "https://fake-site.com/book/1"])
    monkeypatch.setattr(
        "stories_crawl.cli.build_translator", lambda **kw: FakeTranslator()
    )
    cli.invoke(main, ["translate", "Truyện-Giả"])
    result = cli.invoke(main, ["list"])
    assert "dịch 2/2" in result.output
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `.venv/bin/pytest tests/test_cli.py -k translate -v`
Expected: FAIL (chưa có lệnh `translate` / `TRANSLATE_KWARGS`).

- [ ] **Step 3: Sửa `cli.py`**

Thêm import ở đầu file (sau các import hiện có):

```python
from .storage.glossary import read_glossary
from .translate.base import TranslateError
from .translate.registry import build_translator
from .core.translator_loop import translate_pending
```

Thêm hằng số cạnh `DOWNLOAD_KWARGS`:

```python
# test ghi đè để tắt sleep khi dịch
TRANSLATE_KWARGS: dict = {}
```

Thêm lệnh `translate` (đặt sau lệnh `update`):

```python
@main.command()
@click.argument("key")
@click.option("--provider", help="claude | openai | lmstudio | ollama (ghi đè env)")
@click.option("--model", help="Tên model (ghi đè env)")
@click.option("--base-url", help="Endpoint OpenAI-compatible (ghi đè env/preset)")
@click.option("--limit", type=int, help="Chỉ dịch tối đa N chương")
@click.option("--retranslate", is_flag=True, help="Dịch lại cả chương đã dịch")
def translate(key, provider, model, base_url, limit, retranslate):
    """Dịch các chương đã tải của một truyện sang tiếng Việt."""
    lib_dir = _library_dir()
    lib = Library(lib_dir / "library.db")
    try:
        row = lib.get_novel(key)
        if row is None:
            raise click.ClickException(f"Không tìm thấy truyện: {key}")
        try:
            translator = build_translator(
                provider=provider, model=model, base_url=base_url
            )
        except TranslateError as e:
            raise click.ClickException(str(e))
        glossary = read_glossary(lib_dir, row["slug"])
        try:
            summary = translate_pending(
                translator, lib, lib_dir, row, glossary,
                limit=limit, include_done=retranslate,
                log=click.echo, **TRANSLATE_KWARGS,
            )
        finally:
            translator.close()
        click.echo(f"Dịch xong: {summary.done} OK, {summary.failed} lỗi")
        for idx, title, err in summary.failures:
            click.echo(f"  - chương {idx} ({title}): {err}")
    finally:
        lib.close()
```

Sửa `list_cmd` để in thêm tiến độ dịch:

```python
        for r in rows:
            click.echo(
                f"[{r['id']}] {r['title']} ({r['slug']})"
                f" — {r['done_count']}/{r['total_count']} chương"
                f" — dịch {r['translated_count']}/{r['total_count']}"
                f" — {r['status']}"
            )
```

- [ ] **Step 4: Chạy toàn bộ test, xác nhận pass**

Run: `.venv/bin/pytest tests/ -v`
Expected: tất cả pass (bộ cũ 48 + test dịch mới).

- [ ] **Step 5: Thêm extra `[translate]` vào `pyproject.toml`**

```toml
[project.optional-dependencies]
dev = ["pytest>=8"]
translate = ["anthropic>=0.40", "openai>=1.40"]
```

- [ ] **Step 6: Cập nhật README**

Thêm mục sau phần "Vượt Cloudflare":

```markdown
## Dịch tiếng Việt (tùy chọn)

Dịch các chương đã tải sang tiếng Việt bằng LLM. Cài thêm:

    pip install -e '.[translate]'

Cấu hình một lần qua biến môi trường (khuyến nghị), rồi chỉ cần `crawl translate <slug>`:

    # Claude (nhúng API key của bạn)
    export STORIES_TRANSLATOR=claude
    export STORIES_TRANSLATE_MODEL=claude-opus-4-8
    export STORIES_TRANSLATE_API_KEY=sk-ant-...

    # hoặc OpenAI/ChatGPT
    export STORIES_TRANSLATOR=openai
    export STORIES_TRANSLATE_MODEL=gpt-4o
    export STORIES_TRANSLATE_API_KEY=sk-...

    # hoặc LLM local (LM Studio / Ollama) — không tốn phí
    export STORIES_TRANSLATOR=ollama          # hoặc lmstudio
    export STORIES_TRANSLATE_MODEL=qwen2.5

    crawl translate <slug>        # dịch chương chưa dịch (resume được)
    crawl translate <slug> --limit 5          # thử vài chương trước
    crawl translate <slug> --provider lmstudio --model <tên>  # ghi đè tạm

Bản dịch lưu ở `library/<slug>/vi/`. Đặt file `library/<slug>/glossary.md`
(mỗi dòng `Hán = Việt`) để giữ nhất quán tên riêng/thuật ngữ giữa các chương.

`crawl translate` là lệnh riêng — chạy `crawl add`/`update` không dịch gì.
```

- [ ] **Step 7: Smoke test thật (thủ công)**

Với LM Studio (hoặc Ollama) đang bật một model:

```bash
STORIES_TRANSLATOR=lmstudio STORIES_TRANSLATE_MODEL=<tên-model-đang-nạp> \
  .venv/bin/crawl translate <slug> --limit 2
```

Kiểm tra: `library/<slug>/vi/` có 2 file `.md` tiếng Việt hợp lý; `crawl list`
hiện `dịch 2/N`. Thử lại với Claude nếu có API key. Nếu backend chưa bật →
báo lỗi thân thiện, không traceback. Ghi kết quả vào commit.

- [ ] **Step 8: Commit**

```bash
git add stories_crawl/cli.py pyproject.toml README.md tests/test_cli.py
git commit -m "feat: crawl translate command + translate extra and docs"
```

---

## Self-review đã thực hiện

- **Spec coverage:** interface + 2 backend (Task 3/4/5), registry + preset + OpenAI/ChatGPT (Task 6), env-first config (Task 6/8), lệnh `translate` opt-in + `--retranslate`/`--limit` (Task 8), lưu `vi/` + migration DB (Task 1/2), glossary thủ công (Task 2/8), resume/lỗi/min_ratio (Task 7), extra `[translate]` + README + smoke (Task 8). Batch API cố ý ngoài phạm vi (spec ghi rõ).
- **Placeholder scan:** không có TODO/TBD; mọi step có mã đầy đủ.
- **Type consistency:** `Translator.translate_chapter(title, text, glossary=None) -> TranslatedChapter(title, text)` nhất quán Task 3→4→5→7; `build_translator(provider, model, base_url, api_key)` nhất quán Task 6→8; `translate_pending(translator, lib, library_dir, novel, glossary, *, limit, include_done, ...)` nhất quán Task 7→8; `write_chapter(..., subdir=)` và `read_chapter_body` Task 2→7; `pending_translations(novel_id, include_done)` Task 1→7. `FakeTranslator` (conftest) dùng chung Task 7→8.
- **Rủi ro còn lại (Task 8 smoke test):** định dạng đầu ra `NHAN ĐỀ:` phụ thuộc model tuân thủ — `parse_translation` có fallback (dùng title gốc) nên không vỡ; chất lượng dịch model local là vấn đề vận hành, không phải đúng/sai code.
```
