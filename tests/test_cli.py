import pytest
from click.testing import CliRunner

from stories_crawl.adapters.base import BaseAdapter, ChapterRef, NovelInfo
from stories_crawl.cli import _looks_blocked, main
from stories_crawl.core import registry
from stories_crawl.storage.db import Library

from conftest import FakeAdapter, FakeTranslator


class _Summary:
    def __init__(self, done, failed):
        self.done = done
        self.failed = failed


def test_looks_blocked_heuristic():
    # 100% thất bại → bị chặn (giữ hành vi cũ)
    assert _looks_blocked(_Summary(done=0, failed=2)) is True
    # tải được một phần rồi phần còn lại bị chặn (lỗi >= thành công) → bị chặn
    assert _looks_blocked(_Summary(done=5, failed=10)) is True
    assert _looks_blocked(_Summary(done=5, failed=5)) is True
    # chỉ vài chương hỏng thật giữa nhiều chương OK → KHÔNG kích hoạt fallback
    assert _looks_blocked(_Summary(done=100, failed=2)) is False
    # không lỗi → không bị chặn
    assert _looks_blocked(_Summary(done=10, failed=0)) is False


@pytest.fixture
def runner(tmp_path, monkeypatch):
    monkeypatch.setenv("STORIES_LIBRARY", str(tmp_path / "library"))
    monkeypatch.setattr(registry, "NATIVE_ADAPTERS", [FakeAdapter])
    # downloader chạy thật nhưng không ngủ
    monkeypatch.setattr("stories_crawl.cli.DOWNLOAD_KWARGS", {"sleep": lambda _: None})
    return CliRunner(), tmp_path / "library"


class FakeBlockingAdapter(BaseAdapter):
    """Chế độ nhanh (fetcher=None) trả rỗng; có fetcher thì trả chương thật."""

    name = "fakeblock"

    def __init__(self, url, *, fetcher=None):
        super().__init__(url)
        self.fetcher = fetcher

    @classmethod
    def supports(cls, url):
        return "block-site.com" in url

    def get_novel_info(self, url):
        if self.fetcher is None:
            return NovelInfo(title="", author="", url=url, chapters=[])
        return NovelInfo(
            title="Truyện Chặn", author="TG", url=url,
            chapters=[ChapterRef(1, "Chương 1", url + "/1"),
                      ChapterRef(2, "Chương 2", url + "/2")],
        )

    def get_chapter(self, chapter_url):
        return "nội dung dài " * 50

    def close(self):
        pass


class FakeClientCM:
    """Giả FlareSolverrClient: context manager không cần mạng."""

    last = None

    def __init__(self, endpoint, **kw):
        self.endpoint = endpoint
        FakeClientCM.last = self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def fetch(self, url):
        return "x"


@pytest.fixture
def block_runner(tmp_path, monkeypatch):
    monkeypatch.setenv("STORIES_LIBRARY", str(tmp_path / "library"))
    monkeypatch.setattr(registry, "NATIVE_ADAPTERS", [FakeBlockingAdapter])
    monkeypatch.setattr("stories_crawl.cli.DOWNLOAD_KWARGS", {"sleep": lambda _: None})
    monkeypatch.setattr("stories_crawl.cli.FlareSolverrClient", FakeClientCM)
    return CliRunner(), tmp_path / "library"


def test_add_falls_back_to_flaresolverr(block_runner):
    cli, lib_dir = block_runner
    result = cli.invoke(main, ["add", "https://block-site.com/book/1"])
    assert result.exit_code == 0, result.output
    assert "FlareSolverr" in result.output
    assert "Truyện Chặn" in result.output
    assert "2 OK" in result.output
    assert (lib_dir / "Truyện-Chặn" / "raw" / "0001-Chương-1.md").exists()
    assert FakeClientCM.last is not None  # client đã được mở


def test_no_browser_flag_skips_fallback(block_runner):
    cli, _ = block_runner
    FakeClientCM.last = None
    result = cli.invoke(main, ["add", "--no-browser", "https://block-site.com/book/1"])
    assert result.exit_code != 0
    assert "no-browser" in result.output.lower() or "FlareSolverr" in result.output
    assert FakeClientCM.last is None  # không mở client


def test_add_downloads_novel(runner):
    cli, lib_dir = runner
    result = cli.invoke(main, ["add", "https://fake-site.com/book/1"])
    assert result.exit_code == 0, result.output
    assert "Truyện Giả" in result.output
    assert "2 OK, 0 lỗi" in result.output
    assert (lib_dir / "Truyện-Giả" / "raw" / "0001-Chương-1.md").exists()


def test_add_unsupported_source(runner, monkeypatch):
    cli, _ = runner
    from stories_crawl.adapters.lncrawl_bridge import LncrawlAdapter

    monkeypatch.setattr(registry, "NATIVE_ADAPTERS", [])
    monkeypatch.setattr(LncrawlAdapter, "supports", classmethod(lambda cls, url: False))
    result = cli.invoke(main, ["add", "https://unknown-site.example/book/1"])
    assert result.exit_code != 0
    assert "Nguồn không được hỗ trợ" in result.output
    assert "Traceback" not in result.output


def test_add_metadata_fetch_failure(runner, monkeypatch):
    cli, _ = runner

    def _boom(self, url):
        raise RuntimeError("mất kết nối")

    monkeypatch.setattr(FakeAdapter, "get_novel_info", _boom)
    result = cli.invoke(main, ["add", "--no-browser", "https://fake-site.com/book/1"])
    assert result.exit_code != 0
    assert "bị Cloudflare chặn" in result.output
    assert "Traceback" not in result.output


def test_add_existing_url_resumes(runner):
    cli, lib_dir = runner
    cli.invoke(main, ["add", "https://fake-site.com/book/1"])
    result = cli.invoke(main, ["add", "https://fake-site.com/book/1"])
    assert result.exit_code == 0, result.output
    assert "0 OK, 0 lỗi" in result.output  # không tải lại chương đã done


def test_update_by_slug_and_id(runner):
    cli, lib_dir = runner
    cli.invoke(main, ["add", "https://fake-site.com/book/1"])
    result = cli.invoke(main, ["update", "Truyện-Giả"])
    assert result.exit_code == 0, result.output
    result = cli.invoke(main, ["update", "1"])
    assert result.exit_code == 0, result.output


def test_update_unknown_novel(runner):
    cli, _ = runner
    result = cli.invoke(main, ["update", "không-có"])
    assert result.exit_code != 0
    assert "Không tìm thấy" in result.output


def test_list_shows_progress(runner):
    cli, _ = runner
    cli.invoke(main, ["add", "https://fake-site.com/book/1"])
    result = cli.invoke(main, ["list"])
    assert result.exit_code == 0, result.output
    assert "Truyện Giả" in result.output
    assert "2/2" in result.output


def test_list_empty(runner):
    cli, _ = runner
    result = cli.invoke(main, ["list"])
    assert result.exit_code == 0
    assert "Kho trống" in result.output


def test_sources(runner, monkeypatch):
    cli, _ = runner
    monkeypatch.setattr(
        "stories_crawl.adapters.lncrawl_bridge.list_supported_domains",
        lambda language="zh": ["69shuba.com", "uukanshu.cc"],
    )
    result = cli.invoke(main, ["sources"])
    assert result.exit_code == 0, result.output
    assert "69shuba.com" in result.output


@pytest.fixture
def trans_runner(tmp_path, monkeypatch):
    monkeypatch.setenv("STORIES_LIBRARY", str(tmp_path / "library"))
    monkeypatch.setattr(registry, "NATIVE_ADAPTERS", [FakeAdapter])
    monkeypatch.setattr("stories_crawl.cli.DOWNLOAD_KWARGS", {"sleep": lambda _: None})
    monkeypatch.setattr("stories_crawl.cli.TRANSLATE_KWARGS", {"sleep": lambda _: None})
    return CliRunner(), tmp_path / "library"


def test_translate_command(trans_runner, monkeypatch):
    cli, lib_dir = trans_runner
    cli.invoke(main, ["add", "https://fake-site.com/book/1"])  # crawl trước
    monkeypatch.setattr(
        "stories_crawl.cli.build_translator", lambda **kw: FakeTranslator()
    )
    result = cli.invoke(main, ["translate", "Truyện-Giả"])
    assert result.exit_code == 0, result.output
    assert "Dịch xong: 2 OK" in result.output
    assert (lib_dir / "Truyện-Giả" / "vi" / "0001-[VI]-Chương-1.md").exists()


def test_translate_unknown_novel(trans_runner):
    cli, _ = trans_runner
    result = cli.invoke(main, ["translate", "không-có"])
    assert result.exit_code != 0
    assert "Không tìm thấy" in result.output


def test_translate_config_error(trans_runner, monkeypatch):
    cli, _ = trans_runner
    cli.invoke(main, ["add", "https://fake-site.com/book/1"])
    from stories_crawl.translate.base import TranslateError

    def _boom(**kw):
        raise TranslateError("Chưa cấu hình provider dịch")

    monkeypatch.setattr("stories_crawl.cli.build_translator", _boom)
    result = cli.invoke(main, ["translate", "Truyện-Giả"])
    assert result.exit_code != 0
    assert "provider" in result.output


def test_list_shows_translation_progress(trans_runner, monkeypatch):
    cli, _ = trans_runner
    cli.invoke(main, ["add", "https://fake-site.com/book/1"])
    monkeypatch.setattr(
        "stories_crawl.cli.build_translator", lambda **kw: FakeTranslator()
    )
    cli.invoke(main, ["translate", "Truyện-Giả"])
    result = cli.invoke(main, ["list"])
    assert "dịch 2/2" in result.output
