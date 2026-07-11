from types import SimpleNamespace

import pytest

from stories_crawl.translate.anthropic import AnthropicTranslator
from stories_crawl.translate.base import TranslateError


class FakeMessages:
    def __init__(self, blocks=None, error=None, stop_reason=None):
        self._blocks = blocks or []
        self._error = error
        self._stop_reason = stop_reason
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return SimpleNamespace(content=self._blocks, stop_reason=self._stop_reason)


class FakeClient:
    def __init__(self, blocks=None, error=None, stop_reason=None):
        self.messages = FakeMessages(blocks=blocks, error=error, stop_reason=stop_reason)


def _text_block(t):
    return SimpleNamespace(type="text", text=t)


def test_translate_ok():
    client = FakeClient(blocks=[_text_block("NHAN ĐỀ: Chương 1\n\nBản dịch dài.")])
    t = AnthropicTranslator(model="claude-opus-4-8", client=client)
    out = t.translate_chapter("第一章", "原文")
    assert out.title == "Chương 1"
    assert "Bản dịch" in out.text
    assert client.messages.calls[0]["model"] == "claude-opus-4-8"
    # dùng system (không phải role system trong messages)
    assert "tiếng Việt" in client.messages.calls[0]["system"]


def test_translate_empty_raises():
    t = AnthropicTranslator(model="m", client=FakeClient(blocks=[_text_block("  ")]))
    with pytest.raises(TranslateError):
        t.translate_chapter("t", "x")


def test_translate_truncated_raises():
    client = FakeClient(
        blocks=[_text_block("NHAN ĐỀ: t\n\nnội dung bị cắt")],
        stop_reason="max_tokens",
    )
    t = AnthropicTranslator(model="m", client=client)
    with pytest.raises(TranslateError):
        t.translate_chapter("t", "x")


def test_translate_error_wrapped():
    t = AnthropicTranslator(model="m", client=FakeClient(error=RuntimeError("boom")))
    with pytest.raises(TranslateError):
        t.translate_chapter("t", "x")


def test_translate_malformed_response_wrapped():
    class MalformedMessages:
        @staticmethod
        def create(**kwargs):
            return SimpleNamespace(content=None)

    class MalformedClient:
        def __init__(self):
            self.messages = MalformedMessages()

    t = AnthropicTranslator(model="m", client=MalformedClient())
    with pytest.raises(TranslateError):
        t.translate_chapter("t", "x")
