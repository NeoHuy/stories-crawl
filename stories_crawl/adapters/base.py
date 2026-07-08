from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ChapterRef:
    idx: int
    title: str
    url: str


@dataclass
class NovelInfo:
    title: str
    author: str
    url: str
    chapters: list = field(default_factory=list)


class UnsupportedSourceError(Exception):
    pass


class BaseAdapter(ABC):
    name: str = "base"

    def __init__(self, url: str):
        self.url = url

    @classmethod
    @abstractmethod
    def supports(cls, url: str) -> bool: ...

    @abstractmethod
    def get_novel_info(self, url: str) -> NovelInfo: ...

    @abstractmethod
    def get_chapter(self, chapter_url: str) -> str: ...

    def close(self) -> None:
        pass
