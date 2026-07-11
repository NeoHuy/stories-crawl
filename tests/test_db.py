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


def _chapter(lib, novel_id, idx):
    return lib.conn.execute(
        "SELECT * FROM chapters WHERE novel_id = ? AND idx = ?", (novel_id, idx)
    ).fetchone()


def test_add_chapters_upserts_title_url_for_non_done(lib):
    novel_id = _add_novel(lib)
    lib.add_chapters(novel_id, [Ref(1, "第一章", "https://example.com/c/1"),
                                Ref(2, "第二章", "https://example.com/c/2")])
    # chương 1 đã tải xong; chương 2 vẫn pending
    done_id = _chapter(lib, novel_id, 1)["id"]
    lib.mark_chapter_done(done_id, "斗破苍穹/raw/0001.md")

    # nguồn đổi URL/title cho cả hai + thêm chương 3
    inserted = lib.add_chapters(novel_id, [
        Ref(1, "第一章-sửa", "https://example.com/c/1-new"),
        Ref(2, "第二章-sửa", "https://example.com/c/2-new"),
        Ref(3, "第三章", "https://example.com/c/3"),
    ])
    assert inserted == 1  # chỉ chương 3 là mới

    # chương 2 (chưa done) được cập nhật URL/title mới
    ch2 = _chapter(lib, novel_id, 2)
    assert ch2["title"] == "第二章-sửa"
    assert ch2["source_url"] == "https://example.com/c/2-new"

    # chương 1 (đã done) KHÔNG bị đụng
    ch1 = _chapter(lib, novel_id, 1)
    assert ch1["title"] == "第一章"
    assert ch1["source_url"] == "https://example.com/c/1"
    assert ch1["crawl_status"] == "done"


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
