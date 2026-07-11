from types import SimpleNamespace

import pytest

from stories_crawl.translate.base import TranslateError
from stories_crawl.translate.openai_compat import OpenAICompatTranslator


class FakeChat:
    def __init__(self, content=None, error=None):
        self._content = content
        self._error = error
        self.calls = []

    class _Completions:
        def __init__(self, outer):
            self.outer = outer

        def create(self, **kwargs):
            self.outer.calls.append(kwargs)
            if self.outer._error:
                raise self.outer._error
            msg = SimpleNamespace(content=self.outer._content)
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    @property
    def completions(self):
        return FakeChat._Completions(self)


class FakeClient:
    def __init__(self, content=None, error=None):
        self.chat = FakeChat(content=content, error=error)


def test_translate_ok():
    client = FakeClient(content="NHAN ĐỀ: Chương 1\n\nNội dung dịch dài.")
    t = OpenAICompatTranslator(model="qwen", base_url="http://x/v1", client=client)
    out = t.translate_chapter("第一章", "原文", glossary="炎少 = Viêm thiếu")
    assert out.title == "Chương 1"
    assert "Nội dung dịch" in out.text
    # gửi đúng model + có system chứa glossary
    kw = client.chat.calls[0]
    assert kw["model"] == "qwen"
    assert any("炎少" in m["content"] for m in kw["messages"] if m["role"] == "system")


def test_translate_empty_raises():
    t = OpenAICompatTranslator(model="m", base_url="http://x/v1",
                               client=FakeClient(content="   "))
    with pytest.raises(TranslateError):
        t.translate_chapter("t", "x")


def test_translate_network_error_wrapped():
    t = OpenAICompatTranslator(model="m", base_url="http://x/v1",
                               client=FakeClient(error=ConnectionError("down")))
    with pytest.raises(TranslateError):
        t.translate_chapter("t", "x")


class MalformedChat:
    class _Completions:
        @staticmethod
        def create(**kwargs):
            return SimpleNamespace(choices=[])

    @property
    def completions(self):
        return MalformedChat._Completions()


class MalformedClient:
    def __init__(self):
        self.chat = MalformedChat()


def test_translate_malformed_response_wrapped():
    t = OpenAICompatTranslator(model="m", base_url="http://x/v1",
                               client=MalformedClient())
    with pytest.raises(TranslateError):
        t.translate_chapter("t", "x")
