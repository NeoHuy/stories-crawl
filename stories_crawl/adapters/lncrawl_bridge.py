from .base import BaseAdapter, ChapterRef, NovelInfo


class LncrawlAdapter(BaseAdapter):
    name = "lncrawl"

    @classmethod
    def supports(cls, url: str) -> bool:
        raise NotImplementedError

    def get_novel_info(self, url: str) -> NovelInfo:
        raise NotImplementedError

    def get_chapter(self, chapter_url: str) -> str:
        raise NotImplementedError
