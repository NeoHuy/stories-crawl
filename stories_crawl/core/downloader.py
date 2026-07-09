import random
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..storage.files import write_chapter


class ContentTooShortError(Exception):
    pass


@dataclass
class DownloadSummary:
    done: int = 0
    failed: int = 0
    failures: list = field(default_factory=list)


def download_pending(adapter, lib, library_dir: Path, novel, *,
                     delay_range=(1.0, 2.0), max_retries=3, min_length=200,
                     sleep=time.sleep, log=print) -> DownloadSummary:
    summary = DownloadSummary()
    chapters = lib.pending_chapters(novel["id"])
    for i, ch in enumerate(chapters):
        last_error = ""
        for attempt in range(1, max_retries + 1):
            try:
                text = adapter.get_chapter(ch["source_url"])
                if len(text) < min_length:
                    raise ContentTooShortError(
                        f"Nội dung quá ngắn ({len(text)} ký tự), có thể bị chặn"
                    )
                rel = write_chapter(
                    library_dir, novel["slug"], ch["idx"], ch["title"] or "", text
                )
                lib.mark_chapter_done(ch["id"], rel)
                summary.done += 1
                log(f"  [{ch['idx']:>5}] {ch['title']} — OK")
                break
            except Exception as e:
                last_error = str(e) or type(e).__name__
                if attempt < max_retries:
                    sleep(2 ** (attempt - 1))
        else:
            lib.mark_chapter_failed(ch["id"], last_error)
            summary.failed += 1
            summary.failures.append((ch["idx"], ch["title"] or "", last_error))
            log(f"  [{ch['idx']:>5}] {ch['title']} — LỖI: {last_error}")
        if i < len(chapters) - 1:
            sleep(random.uniform(*delay_range))
    lib.touch_novel(novel["id"])
    if not lib.pending_chapters(novel["id"]):
        lib.set_novel_status(novel["id"], "completed")
    elif summary.failed > 0:
        lib.set_novel_status(novel["id"], "error")
    else:
        lib.set_novel_status(novel["id"], "active")
    return summary
