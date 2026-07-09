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


def test_sanitize_rejects_dot_only_paths():
    # tránh path traversal: kết quả không bao giờ được là "." hoặc ".."
    assert sanitize("..") == "untitled"
    assert sanitize(".") == "untitled"
    assert sanitize("...") == "untitled"
    assert sanitize("..foo") == "foo"
    result = sanitize("..")
    assert result not in (".", "..")
    assert not result.startswith(".")


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
