import pytest

from stories_crawl.adapters.base import (
    BaseAdapter,
    ChapterRef,
    NovelInfo,
    UnsupportedSourceError,
)
from stories_crawl.core import registry


class FakeNative(BaseAdapter):
    name = "fake-native"

    @classmethod
    def supports(cls, url):
        return "fake-site.com" in url

    def get_novel_info(self, url):
        return NovelInfo(title="t", author="a", url=url,
                         chapters=[ChapterRef(1, "c1", url + "/1")])

    def get_chapter(self, chapter_url):
        return "nội dung"


@pytest.fixture(autouse=True)
def clean_natives(monkeypatch):
    monkeypatch.setattr(registry, "NATIVE_ADAPTERS", [FakeNative])


def test_native_adapter_wins(monkeypatch):
    # lncrawl bridge không được gọi khi native đã match
    monkeypatch.setattr(
        "stories_crawl.adapters.lncrawl_bridge.LncrawlAdapter.supports",
        classmethod(lambda cls, url: (_ for _ in ()).throw(AssertionError("not called"))),
    )
    assert registry.find_adapter_class("https://fake-site.com/book/1") is FakeNative


def test_fallback_to_lncrawl(monkeypatch):
    monkeypatch.setattr(
        "stories_crawl.adapters.lncrawl_bridge.LncrawlAdapter.supports",
        classmethod(lambda cls, url: True),
    )
    from stories_crawl.adapters.lncrawl_bridge import LncrawlAdapter
    assert registry.find_adapter_class("https://other.com/x") is LncrawlAdapter


def test_unsupported_raises(monkeypatch):
    monkeypatch.setattr(
        "stories_crawl.adapters.lncrawl_bridge.LncrawlAdapter.supports",
        classmethod(lambda cls, url: False),
    )
    with pytest.raises(UnsupportedSourceError):
        registry.find_adapter_class("https://unknown.org/x")
