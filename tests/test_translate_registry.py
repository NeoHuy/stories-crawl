import pytest

from stories_crawl.translate import registry
from stories_crawl.translate.base import TranslateError


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    for k in ("STORIES_TRANSLATOR", "STORIES_TRANSLATE_MODEL",
              "STORIES_TRANSLATE_BASE_URL", "STORIES_TRANSLATE_API_KEY"):
        monkeypatch.delenv(k, raising=False)


def test_missing_provider_raises():
    with pytest.raises(TranslateError, match="provider"):
        registry.build_translator()


def test_claude_routes_to_anthropic(monkeypatch):
    captured = {}

    class FakeAnthropic:
        def __init__(self, model, api_key=None):
            captured["model"] = model
            captured["api_key"] = api_key

    monkeypatch.setattr(
        "stories_crawl.translate.anthropic.AnthropicTranslator", FakeAnthropic
    )
    registry.build_translator(provider="claude", api_key="sk-x")
    assert captured["model"] == "claude-opus-4-8"  # mặc định
    assert captured["api_key"] == "sk-x"


def test_ollama_preset_base_url(monkeypatch):
    captured = {}

    class FakeOpenAI:
        def __init__(self, model, base_url=None, api_key="not-needed"):
            captured["model"] = model
            captured["base_url"] = base_url

    monkeypatch.setattr(
        "stories_crawl.translate.openai_compat.OpenAICompatTranslator", FakeOpenAI
    )
    registry.build_translator(provider="ollama", model="qwen2.5")
    assert captured["base_url"] == "http://localhost:11434/v1"
    assert captured["model"] == "qwen2.5"


def test_openai_default_base_url_none(monkeypatch):
    captured = {}

    class FakeOpenAI:
        def __init__(self, model, base_url=None, api_key="not-needed"):
            captured["base_url"] = base_url

    monkeypatch.setattr(
        "stories_crawl.translate.openai_compat.OpenAICompatTranslator", FakeOpenAI
    )
    registry.build_translator(provider="openai", model="gpt-4o", api_key="sk")
    assert captured["base_url"] is None  # dùng mặc định SDK openai (OpenAI thật)


def test_openai_missing_model_raises():
    with pytest.raises(TranslateError, match="model"):
        registry.build_translator(provider="lmstudio")


def test_unknown_provider_raises():
    with pytest.raises(TranslateError, match="không hỗ trợ"):
        registry.build_translator(provider="bogus", model="m")


def test_env_defaults(monkeypatch):
    monkeypatch.setenv("STORIES_TRANSLATOR", "ollama")
    monkeypatch.setenv("STORIES_TRANSLATE_MODEL", "llama3.1")
    captured = {}

    class FakeOpenAI:
        def __init__(self, model, base_url=None, api_key="not-needed"):
            captured["model"] = model

    monkeypatch.setattr(
        "stories_crawl.translate.openai_compat.OpenAICompatTranslator", FakeOpenAI
    )
    registry.build_translator()  # không tham số → đọc env
    assert captured["model"] == "llama3.1"
