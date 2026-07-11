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
    for ch in chapters:
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
