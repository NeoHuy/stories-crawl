from .base import TranslateError, TranslatedChapter, Translator
from .prompt import build_system_prompt, build_user_message, parse_translation


class AnthropicTranslator(Translator):
    def __init__(self, model, api_key=None, *, client=None, max_tokens=8000):
        self.model = model
        self.max_tokens = max_tokens
        if client is not None:
            self._client = client
        else:
            try:
                import anthropic
            except ImportError as e:
                raise TranslateError(
                    "Chưa cài SDK anthropic — chạy: pip install -e '.[translate]'"
                ) from e
            self._client = (
                anthropic.Anthropic(api_key=api_key) if api_key
                else anthropic.Anthropic()
            )

    def translate_chapter(self, title, text, glossary=None):
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=build_system_prompt(glossary),
                messages=[
                    {"role": "user", "content": build_user_message(title, text)}
                ],
            )
            parts = [
                b.text for b in resp.content if getattr(b, "type", None) == "text"
            ]
            out = "".join(parts).strip()
        except Exception as e:
            raise TranslateError(f"Lỗi gọi Claude: {e}") from e
        if not out:
            raise TranslateError("Claude trả về rỗng")
        vi_title, vi_text = parse_translation(out, title)
        return TranslatedChapter(title=vi_title, text=vi_text)
