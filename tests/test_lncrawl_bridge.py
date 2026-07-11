from types import SimpleNamespace

import pytest

from stories_crawl.adapters import lncrawl_bridge
from stories_crawl.adapters.lncrawl_bridge import (
    LncrawlAdapter,
    list_supported_domains,
)


class FakeChapter(SimpleNamespace):
    pass


class FakeCrawler:
    def __init__(self):
        self.closed = False

    def read_novel(self, novel):
        novel.title = "斗破苍穹"
        novel.author = "天蚕土豆"
        novel.chapters = [
            FakeChapter(id=1, url="https://x.com/c/1", title="第一章", body=None),
            FakeChapter(id=2, url="https://x.com/c/2", title="第二章", body=None),
        ]

    def download_chapter(self, chapter):
        chapter.body = "<p>你好</p><p>世界</p>"

    def close(self):
        self.closed = True

    def make_soup(self, html):
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser")

    def get_soup(self, url, *a, **k):
        raise AssertionError("scraper get_soup must not be called in browser mode")


class FakeSources:
    def __init__(self):
        self.crawler = FakeCrawler()

    def find_crawler(self, url):
        if "supported.com" not in url:
            raise ValueError("no crawler")
        return FakeCrawler

    def init_crawler(self, url):
        return self.crawler

    def list(self):
        return [
            SimpleNamespace(domain="69shuba.com", file_path="sources/zh/69shuba.py",
                            is_disabled=False),
            SimpleNamespace(domain="dead.com", file_path="sources/zh/dead.py",
                            is_disabled=True),
            SimpleNamespace(domain="royalroad.com", file_path="sources/en/r/royalroad.py",
                            is_disabled=False),
        ]


@pytest.fixture
def fake_sources(monkeypatch):
    fake = FakeSources()
    monkeypatch.setattr(lncrawl_bridge, "_sources", lambda: fake)
    return fake


def test_supports(fake_sources):
    assert LncrawlAdapter.supports("https://supported.com/book/1") is True
    assert LncrawlAdapter.supports("https://nope.com/book/1") is False


def test_get_novel_info(fake_sources):
    adapter = LncrawlAdapter("https://supported.com/book/1")
    info = adapter.get_novel_info("https://supported.com/book/1")
    assert info.title == "斗破苍穹"
    assert info.author == "天蚕土豆"
    assert [(c.idx, c.title, c.url) for c in info.chapters] == [
        (1, "第一章", "https://x.com/c/1"),
        (2, "第二章", "https://x.com/c/2"),
    ]


def test_get_chapter_strips_html(fake_sources):
    adapter = LncrawlAdapter("https://supported.com/book/1")
    adapter.get_novel_info("https://supported.com/book/1")
    text = adapter.get_chapter("https://x.com/c/1")
    assert "你好" in text and "世界" in text
    assert "<p>" not in text


def test_get_chapter_unknown_url_raises_clear_error(fake_sources):
    adapter = LncrawlAdapter("https://supported.com/book/1")
    adapter.get_novel_info("https://supported.com/book/1")
    # URL không có trong mục lục hiện tại → lỗi rõ ràng, không phải KeyError trần
    with pytest.raises(ValueError, match="không có trong mục lục"):
        adapter.get_chapter("https://x.com/c/999")


def test_close_swallows_errors(fake_sources):
    adapter = LncrawlAdapter("https://supported.com/book/1")
    adapter.close()
    assert fake_sources.crawler.closed is True
    fake_sources.crawler.close = lambda: (_ for _ in ()).throw(RuntimeError)
    adapter.close()  # không raise


def test_list_supported_domains(fake_sources):
    assert list_supported_domains() == ["69shuba.com"]
    assert list_supported_domains("en") == ["royalroad.com"]


def test_fetcher_overrides_get_soup(fake_sources):
    from stories_crawl.adapters.lncrawl_bridge import LncrawlAdapter

    class FakeFetcher:
        def __init__(self):
            self.fetched = []

        def fetch(self, url):
            self.fetched.append(url)
            return f"<html><p>{url}</p></html>"

    fetcher = FakeFetcher()
    adapter = LncrawlAdapter("https://supported.com/book/1", fetcher=fetcher)
    soup = adapter._crawler.get_soup("https://supported.com/c/9")
    # đã đi qua fetcher, không chạm scraper
    assert fetcher.fetched == ["https://supported.com/c/9"]
    assert "https://supported.com/c/9" in soup.get_text()
