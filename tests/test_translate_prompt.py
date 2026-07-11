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
