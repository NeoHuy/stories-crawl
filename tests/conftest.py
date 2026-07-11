from stories_crawl.adapters.base import BaseAdapter, ChapterRef, NovelInfo
from stories_crawl.translate.base import TranslatedChapter, Translator


class FakeNetworkError(Exception):
    pass


class FakeAdapter(BaseAdapter):
    """Adapter giả cho test: nội dung cấp sẵn, có thể giả lập lỗi mạng."""

    name = "fake"

    def __init__(self, url="https://fake-site.com/book/1", chapters=None,
                 fail_urls=(), fail_times=99):
        super().__init__(url)
        default = {
            "https://fake-site.com/c/1": "một " * 100,
            "https://fake-site.com/c/2": "hai " * 100,
        }
        self.chapters = chapters if chapters is not None else default
        self.fail_urls = set(fail_urls)
        self.fail_times = fail_times
        self.calls = {}
        self.closed = False

    @classmethod
    def supports(cls, url):
        return "fake-site.com" in url

    def get_novel_info(self, url):
        refs = [
            ChapterRef(i + 1, f"Chương {i + 1}", u)
            for i, u in enumerate(self.chapters)
        ]
        return NovelInfo(title="Truyện Giả", author="Tác Giả", url=url, chapters=refs)

    def get_chapter(self, chapter_url):
        self.calls[chapter_url] = self.calls.get(chapter_url, 0) + 1
        if chapter_url in self.fail_urls and self.calls[chapter_url] <= self.fail_times:
            raise FakeNetworkError("connection reset")
        return self.chapters[chapter_url]

    def close(self):
        self.closed = True


class FakeTranslator(Translator):
    """Translator giả cho test: dịch = thêm tiền tố, có thể giả lập lỗi/rỗng."""

    model = "fake-model"

    def __init__(self, fail_bodies=(), empty_bodies=()):
        self.fail_bodies = set(fail_bodies)   # body nào thì ném lỗi
        self.empty_bodies = set(empty_bodies) # body nào thì trả rỗng
        self.calls = []
        self.closed = False

    def translate_chapter(self, title, text, glossary=None):
        self.calls.append((title, text, glossary))
        if text in self.fail_bodies:
            raise RuntimeError("mô phỏng lỗi dịch")
        if text in self.empty_bodies:
            return TranslatedChapter(title=f"[VI] {title}", text="")
        return TranslatedChapter(title=f"[VI] {title}", text=f"[VI] {text}")

    def close(self):
        self.closed = True
