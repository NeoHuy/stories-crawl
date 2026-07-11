from abc import ABC, abstractmethod
from dataclasses import dataclass


class TranslateError(Exception):
    pass


@dataclass
class TranslatedChapter:
    title: str
    text: str


class Translator(ABC):
    @abstractmethod
    def translate_chapter(self, title: str, text: str,
                          glossary: str | None = None) -> TranslatedChapter: ...

    def close(self) -> None:
        pass
