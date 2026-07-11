import os

from .base import TranslateError

_OPENAI_PRESETS = {
    "lmstudio": "http://localhost:1234/v1",
    "ollama": "http://localhost:11434/v1",
    "openai": None,  # None → SDK openai dùng mặc định api.openai.com (OpenAI thật)
}


def build_translator(provider=None, model=None, base_url=None, api_key=None):
    provider = provider or os.environ.get("STORIES_TRANSLATOR")
    model = model or os.environ.get("STORIES_TRANSLATE_MODEL")
    base_url = base_url or os.environ.get("STORIES_TRANSLATE_BASE_URL")
    api_key = api_key or os.environ.get("STORIES_TRANSLATE_API_KEY")

    if not provider:
        raise TranslateError(
            "Chưa cấu hình provider dịch (đặt STORIES_TRANSLATOR hoặc dùng --provider)"
        )

    if provider in ("claude", "anthropic"):
        from .anthropic import AnthropicTranslator

        return AnthropicTranslator(
            model=model or "claude-opus-4-8", api_key=api_key
        )

    if provider in _OPENAI_PRESETS:
        from .openai_compat import OpenAICompatTranslator

        if not model:
            raise TranslateError(
                "Thiếu model dịch (đặt STORIES_TRANSLATE_MODEL hoặc dùng --model)"
            )
        resolved = base_url or _OPENAI_PRESETS[provider]
        return OpenAICompatTranslator(
            model=model, base_url=resolved, api_key=api_key or "not-needed"
        )

    raise TranslateError(f"Provider dịch không hỗ trợ: {provider}")
