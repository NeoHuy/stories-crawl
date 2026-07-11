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
