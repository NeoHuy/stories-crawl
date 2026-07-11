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
