import pytest

from stories_crawl.core.translator_loop import translate_pending
from stories_crawl.storage.db import Library
from stories_crawl.storage.files import write_chapter

from conftest import FakeTranslator


def _no_sleep(_):
    pass


@pytest.fixture
def env(tmp_path):
    lib = Library(tmp_path / "library.db")
    novel_id = lib.create_novel("truyen", "Truyện", "TG",
                                "https://x.com/b", "fake")

    class Ref:
        def __init__(self, idx, title, url):
            self.idx = idx
            self.title = title
            self.url = url

    lib.add_chapters(novel_id, [Ref(1, "第一章", "u1"), Ref(2, "第二章", "u2")])
    # crawl xong 2 chương: ghi raw + đánh dấu done
    for idx, title, body in [(1, "第一章", "正文一" * 50), (2, "第二章", "正文二" * 50)]:
        rel = write_chapter(tmp_path, "truyen", idx, title, body)
        ch = next(r for r in lib.pending_chapters(novel_id) if r["idx"] == idx)
        lib.mark_chapter_done(ch["id"], rel)
    novel = lib.get_novel(str(novel_id))
    yield tmp_path, lib, novel
    lib.close()


def test_translates_all_pending(env):
    tmp_path, lib, novel = env
    t = FakeTranslator()
    summary = translate_pending(t, lib, tmp_path, novel, sleep=_no_sleep,
                                log=lambda *_: None)
    assert (summary.done, summary.failed) == (2, 0)
    assert lib.pending_translations(novel["id"]) == []
    f = tmp_path / "truyen" / "vi" / "0001-[VI]-第一章.md"
    assert f.read_text(encoding="utf-8").startswith("# [VI] 第一章")


def test_limit(env):
    tmp_path, lib, novel = env
    summary = translate_pending(FakeTranslator(), lib, tmp_path, novel, limit=1,
                                sleep=_no_sleep, log=lambda *_: None)
    assert summary.done == 1
    assert len(lib.pending_translations(novel["id"])) == 1


def test_failure_marks_failed(env):
    tmp_path, lib, novel = env
    t = FakeTranslator(fail_bodies={"正文一" * 50})
    summary = translate_pending(t, lib, tmp_path, novel, sleep=_no_sleep,
                                log=lambda *_: None)
    assert (summary.done, summary.failed) == (1, 1)
    assert [r["idx"] for r in lib.pending_translations(novel["id"])] == [1]


def test_empty_translation_marks_failed(env):
    tmp_path, lib, novel = env
    t = FakeTranslator(empty_bodies={"正文一" * 50})
    summary = translate_pending(t, lib, tmp_path, novel, sleep=_no_sleep,
                                log=lambda *_: None)
    assert summary.failed == 1
    assert not (tmp_path / "truyen" / "vi" / "0001-[VI]-第一章.md").exists()


def test_resume_skips_done(env):
    tmp_path, lib, novel = env
    translate_pending(FakeTranslator(), lib, tmp_path, novel, sleep=_no_sleep,
                      log=lambda *_: None)
    t2 = FakeTranslator()
    summary = translate_pending(t2, lib, tmp_path, novel, sleep=_no_sleep,
                                log=lambda *_: None)
    assert (summary.done, summary.failed) == (0, 0)
    assert t2.calls == []


def test_retranslate_includes_done(env):
    tmp_path, lib, novel = env
    translate_pending(FakeTranslator(), lib, tmp_path, novel, sleep=_no_sleep,
                      log=lambda *_: None)
    t2 = FakeTranslator()
    summary = translate_pending(t2, lib, tmp_path, novel, include_done=True,
                                sleep=_no_sleep, log=lambda *_: None)
    assert summary.done == 2  # dịch lại cả 2
