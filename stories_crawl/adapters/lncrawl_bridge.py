import threading

from bs4 import BeautifulSoup

from .base import BaseAdapter, ChapterRef, NovelInfo

_lock = threading.Lock()
_loaded = False


def _sources():
    """Nạp registry nguồn của lncrawl (lần đầu chạy sẽ sync index từ GitHub)."""
    global _loaded
    from lncrawl.context import ctx

    with _lock:
        if not _loaded:
            ctx.sources.load(sync_remote=True)
            ctx.sources.ensure_load()
            _loaded = True
    return ctx.sources


def list_supported_domains(language: str = "zh") -> list:
    prefix = f"sources/{language}/"
    items = _sources().list()
    return sorted(
        i.domain
        for i in items
        if i.file_path.startswith(prefix) and not i.is_disabled
    )


class LncrawlAdapter(BaseAdapter):
    name = "lncrawl"

    def __init__(self, url: str, *, fetcher=None):
        super().__init__(url)
        self._crawler = _sources().init_crawler(url)
        self._chapter_map = {}
        if fetcher is not None:
            crawler = self._crawler
            crawler.get_soup = lambda u, *a, **k: crawler.make_soup(fetcher.fetch(u))

    @classmethod
    def supports(cls, url: str) -> bool:
        try:
            _sources().find_crawler(url)
            return True
        except Exception:
            return False

    def get_novel_info(self, url: str) -> NovelInfo:
        from lncrawl.core import Novel

        novel = Novel(url=url)
        self._crawler.read_novel(novel)
        refs = []
        for ch in novel.chapters:
            self._chapter_map[ch.url] = ch
            refs.append(ChapterRef(idx=ch.id, title=ch.title or "", url=ch.url))
        return NovelInfo(
            title=novel.title, author=novel.author or "", url=url, chapters=refs
        )

    def get_chapter(self, chapter_url: str) -> str:
        ch = self._chapter_map.get(chapter_url)
        if ch is None:
            # Chương không còn trong mục lục hiện tại (nguồn đã xóa/đổi URL).
            # Báo lỗi rõ ràng thay vì KeyError trần để log dễ hiểu.
            raise ValueError(
                f"Chương không có trong mục lục hiện tại: {chapter_url}"
            )
        self._crawler.download_chapter(ch)
        html = ch.body or ""
        return BeautifulSoup(html, "html.parser").get_text("\n").strip()

    def close(self) -> None:
        try:
            self._crawler.close()
        except Exception:
            pass
