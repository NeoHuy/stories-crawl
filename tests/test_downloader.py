import pytest

from stories_crawl.core.downloader import download_pending
from stories_crawl.storage.db import Library

from conftest import FakeAdapter


@pytest.fixture
def env(tmp_path):
    lib = Library(tmp_path / "library.db")
    adapter = FakeAdapter()
    info = adapter.get_novel_info(adapter.url)
    novel_id = lib.create_novel("truyen-gia", info.title, info.author,
                                adapter.url, adapter.name)
    lib.add_chapters(novel_id, info.chapters)
    novel = lib.get_novel(str(novel_id))
    yield tmp_path, lib, adapter, novel
    lib.close()


def _no_sleep(_):
    pass


def test_downloads_all_pending(env):
    tmp_path, lib, adapter, novel = env
    summary = download_pending(adapter, lib, tmp_path, novel,
                               sleep=_no_sleep, log=lambda *_: None)
    assert (summary.done, summary.failed) == (2, 0)
    assert lib.pending_chapters(novel["id"]) == []
    f = tmp_path / "truyen-gia" / "raw" / "0001-Chương-1.md"
    assert f.read_text(encoding="utf-8").startswith("# Chương 1")


def test_retry_then_success(env):
    tmp_path, lib, adapter, novel = env
    adapter.fail_urls = {"https://fake-site.com/c/1"}
    adapter.fail_times = 2  # fail 2 lần đầu, lần 3 OK
    summary = download_pending(adapter, lib, tmp_path, novel,
                               sleep=_no_sleep, log=lambda *_: None)
    assert (summary.done, summary.failed) == (2, 0)
    assert adapter.calls["https://fake-site.com/c/1"] == 3


def test_exhausted_retries_marks_failed(env):
    tmp_path, lib, adapter, novel = env
    adapter.fail_urls = {"https://fake-site.com/c/2"}  # luôn fail
    summary = download_pending(adapter, lib, tmp_path, novel,
                               sleep=_no_sleep, log=lambda *_: None)
    assert (summary.done, summary.failed) == (1, 1)
    assert summary.failures[0][0] == 2
    assert "connection reset" in summary.failures[0][2]
    # chương failed vẫn pending để lần sau retry
    assert [r["idx"] for r in lib.pending_chapters(novel["id"])] == [2]
    # file của chương failed không được tạo
    assert not (tmp_path / "truyen-gia" / "raw" / "0002-Chương-2.md").exists()


def test_short_content_marks_failed(env):
    tmp_path, lib, adapter, novel = env
    adapter.chapters["https://fake-site.com/c/1"] = "ngắn"
    summary = download_pending(adapter, lib, tmp_path, novel,
                               sleep=_no_sleep, log=lambda *_: None)
    assert (summary.done, summary.failed) == (1, 1)
    assert not (tmp_path / "truyen-gia" / "raw" / "0001-Chương-1.md").exists()


def test_resume_skips_done(env):
    tmp_path, lib, adapter, novel = env
    download_pending(adapter, lib, tmp_path, novel,
                     sleep=_no_sleep, log=lambda *_: None)
    adapter.calls.clear()
    summary = download_pending(adapter, lib, tmp_path, novel,
                               sleep=_no_sleep, log=lambda *_: None)
    assert (summary.done, summary.failed) == (0, 0)
    assert adapter.calls == {}
