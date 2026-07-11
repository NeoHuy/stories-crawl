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
