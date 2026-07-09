import re
from pathlib import Path

_INVALID = re.compile(r'[\\/:*?"<>|\s]+')


def sanitize(name: str) -> str:
    cleaned = _INVALID.sub("-", name).strip("-")
    # tránh path traversal: "." hoặc ".." (hay chuỗi toàn dấu chấm) không
    # được phép trở thành thành phần đường dẫn
    cleaned = cleaned.lstrip(".")
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
