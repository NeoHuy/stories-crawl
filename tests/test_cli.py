import pytest
from click.testing import CliRunner

from stories_crawl.cli import main
from stories_crawl.core import registry
from stories_crawl.storage.db import Library

from conftest import FakeAdapter


@pytest.fixture
def runner(tmp_path, monkeypatch):
    monkeypatch.setenv("STORIES_LIBRARY", str(tmp_path / "library"))
    monkeypatch.setattr(registry, "NATIVE_ADAPTERS", [FakeAdapter])
    # downloader chạy thật nhưng không ngủ
    monkeypatch.setattr("stories_crawl.cli.DOWNLOAD_KWARGS", {"sleep": lambda _: None})
    return CliRunner(), tmp_path / "library"


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
    result = cli.invoke(main, ["add", "https://fake-site.com/book/1"])
    assert result.exit_code != 0
    assert "Không lấy được thông tin truyện" in result.output
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
