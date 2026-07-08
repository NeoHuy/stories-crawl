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
