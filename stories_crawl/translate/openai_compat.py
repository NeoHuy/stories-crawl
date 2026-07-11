from .base import TranslateError, TranslatedChapter, Translator
from .prompt import build_system_prompt, build_user_message, parse_translation


class OpenAICompatTranslator(Translator):
    def __init__(self, model, base_url=None, api_key="not-needed", *,
                 client=None, max_tokens=4096):
        self.model = model
        self.max_tokens = max_tokens
        if client is not None:
            self._client = client
        else:
            try:
                from openai import OpenAI
            except ImportError as e:
                raise TranslateError(
                    "Chưa cài SDK openai — chạy: pip install -e '.[translate]'"
                ) from e
            self._client = OpenAI(base_url=base_url, api_key=api_key)

    def translate_chapter(self, title, text, glossary=None):
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": build_system_prompt(glossary)},
                    {"role": "user", "content": build_user_message(title, text)},
                ],
            )
        except Exception as e:
            raise TranslateError(f"Lỗi gọi backend dịch: {e}") from e
        out = (resp.choices[0].message.content or "").strip()
        if not out:
            raise TranslateError("Backend dịch trả về rỗng")
        vi_title, vi_text = parse_translation(out, title)
        return TranslatedChapter(title=vi_title, text=vi_text)
