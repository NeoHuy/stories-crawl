import re
from pathlib import Path

_INVALID = re.compile(r'[\\/:*?"<>|\s]+')


def sanitize(name: str) -> str:
    cleaned = _INVALID.sub("-", name).strip("-")
    # tránh path traversal: "." hoặc ".." (hay chuỗi toàn dấu chấm) không
    # được phép trở thành thành phần đường dẫn
    cleaned = cleaned.lstrip(".")
    return cleaned or "untitled"


def _truncate_bytes(s: str, max_bytes: int) -> str:
    """Cắt chuỗi còn tối đa max_bytes byte UTF-8, không xẻ đôi ký tự đa byte."""
    encoded = s.encode("utf-8")
    if len(encoded) <= max_bytes:
        return s
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def make_slug(title: str, existing: set) -> str:
    base = sanitize(title)
    slug = base
    n = 2
    while slug in existing:
        slug = f"{base}-{n}"
        n += 1
    return slug


# Giữ tổng filename an toàn dưới giới hạn của hầu hết filesystem (255 byte);
# chừa chỗ cho tiền tố "NNNN-", đuôi ".md" và hậu tố ".tmp" lúc ghi tạm.
_MAX_TITLE_BYTES = 180


def chapter_filename(idx: int, title: str) -> str:
    safe_title = _truncate_bytes(sanitize(title), _MAX_TITLE_BYTES)
    return f"{idx:04d}-{safe_title}.md"


def write_chapter(library_dir: Path, slug: str, idx: int, title: str, text: str) -> str:
    rel = Path(slug) / "raw" / chapter_filename(idx, title)
    path = library_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"# {title}\n\n{text}\n" if title else f"{text}\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
    return rel.as_posix()
