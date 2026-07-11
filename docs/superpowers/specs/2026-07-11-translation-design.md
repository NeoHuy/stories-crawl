# Spec: Dịch truyện Trung → Việt (backend LLM cắm được)

**Ngày:** 2026-07-11
**Trạng thái:** Đã duyệt thiết kế
**Liên quan:** mở rộng tool stories-crawl ([spec gốc](2026-07-08-stories-crawl-design.md))

## Mục đích

Dịch nội dung chương từ tiếng Trung (đã crawl vào `raw/`) sang tiếng Việt bằng
LLM, lưu song song vào `vi/`. Backend dịch **cắm được**: dùng Claude (nhúng API
key) hoặc LLM local qua endpoint tương thích OpenAI (LM Studio, Ollama...). Dịch
là **lệnh riêng, opt-in** — chạy crawl thuần không kích hoạt dịch.

## Quyết định đã chốt (brainstorm)

- Dịch bằng **LLM** (không dùng convert từ điển / MT miễn phí).
- Backend cắm được, **không khóa nhà cung cấp**: Claude + mọi endpoint
  OpenAI-compatible (LM Studio `:1234/v1`, Ollama `:11434/v1`, llama.cpp, vLLM).
  Model bất kỳ sau endpoint đó (Qwen, Llama, Mistral...) đều dùng được.
- **Glossary thủ công tùy chọn** cho nhất quán tên riêng/thuật ngữ; mặc định
  không cần.
- Dịch là **subcommand riêng** `translate`; `add`/`update` không tự dịch.

## Phạm vi

**Trong phạm vi:**
- Interface `Translator` + hai backend: `anthropic` (SDK Anthropic) và
  `openai_compat` (SDK openai, phủ LM Studio/Ollama/llama.cpp...).
- Preset provider trên CLI (`--provider claude|lmstudio|ollama|openai`) tự điền
  `base_url` mặc định; ghi đè được.
- Lệnh `crawl translate <slug|id>` với resume theo từng chương.
- Lưu bản dịch `library/<slug>/vi/NNNN-*.md`; migration DB thêm cột trạng thái dịch.
- Glossary `library/<slug>/glossary.md` (tùy chọn), chèn vào prompt.
- Dependency dịch ở extra `[translate]` — crawler nền vẫn nhẹ.

**Ngoài phạm vi (YAGNI / giai đoạn sau):**
- Batch API của Anthropic (giảm 50%) — ghi nhận là cải tiến sau; MVP dịch tuần tự.
- Tự trích glossary bằng LLM.
- Nhồi ngữ cảnh chương trước (mỗi chương dịch độc lập).
- Prompt caching tinh chỉnh sâu (dùng auto-cache đơn giản cho backend Anthropic).
- Tự động dịch ngay sau crawl (cố ý tách rời).

## Kiến trúc

```
stories_crawl/
├── translate/
│   ├── __init__.py
│   ├── base.py          # Translator (ABC), TranslatedChapter, TranslateError
│   ├── prompt.py        # dựng system prompt + chèn glossary
│   ├── anthropic.py     # AnthropicTranslator (SDK anthropic)
│   ├── openai_compat.py # OpenAICompatTranslator (SDK openai, base_url tùy chỉnh)
│   └── registry.py      # build_translator(config) → chọn backend + preset base_url
├── core/
│   └── translator_loop.py # vòng lặp dịch: pending → gọi → ghi vi/ → cập nhật DB
├── storage/
│   ├── db.py            # SỬA: migration + truy vấn trạng thái dịch
│   └── glossary.py      # MỚI: đọc glossary.md
└── cli.py               # SỬA: lệnh translate + cột dịch trong list
```

### `translate/base.py`

```python
class TranslateError(Exception): ...          # backend không tới được / trả lỗi / rỗng

@dataclass
class TranslatedChapter:
    title: str
    text: str

class Translator(ABC):
    @abstractmethod
    def translate_chapter(self, title: str, text: str, glossary: str | None = None) -> TranslatedChapter: ...
    def close(self) -> None: ...   # mặc định no-op
```

### Hai backend

- **`AnthropicTranslator`**: dùng SDK `anthropic`. `client.messages.create` với
  system = prompt dịch + glossary (auto prompt-cache), user = tiêu đề + nội dung.
  Model mặc định `claude-opus-4-8` (đổi qua config/`--model`). Streaming khi
  `max_tokens` lớn. API key từ `STORIES_TRANSLATE_API_KEY`.
- **`OpenAICompatTranslator`**: dùng SDK `openai` trỏ `base_url` (LM Studio/
  Ollama/...). `chat.completions.create` với message `system` + `user` cùng nội
  dung. Model từ config. `api_key` có thể là chuỗi bất kỳ với server local.

Hai backend ở hai file riêng — không trộn provider trong một file (Claude dùng
SDK Anthropic, phần còn lại dùng SDK openai).

### `translate/registry.py`

`build_translator(provider, model, base_url, api_key) -> Translator`:
- `provider` ∈ `claude`/`anthropic` → `AnthropicTranslator`.
- `provider` ∈ `lmstudio`/`ollama`/`openai` → `OpenAICompatTranslator`, tự điền
  `base_url` mặc định theo preset nếu chưa cho:
  - `lmstudio` → `http://localhost:1234/v1`
  - `ollama` → `http://localhost:11434/v1`
  - `openai` → không mặc định (bắt buộc có `base_url`).

## Cấu hình (env, nhất quán `STORIES_*`)

| Env | Ý nghĩa |
|---|---|
| `STORIES_TRANSLATOR` | provider mặc định: `claude`/`lmstudio`/`ollama`/`openai` |
| `STORIES_TRANSLATE_MODEL` | tên model |
| `STORIES_TRANSLATE_BASE_URL` | endpoint OpenAI-compatible (ghi đè preset) |
| `STORIES_TRANSLATE_API_KEY` | key Claude, hoặc chuỗi bất kỳ cho local |

Cờ CLI `--provider/--model/--base-url` ghi đè env cho lần chạy.

## Lưu trữ & resume

- Bản dịch: `library/<slug>/vi/NNNN-<tiêu đề>.md`, dòng đầu `# <tiêu đề Việt>`
  (dùng lại `write_chapter` với thư mục con `vi`).
- Migration `chapters` (không phá dữ liệu cũ; chạy idempotent lúc mở DB):
  thêm `translate_status TEXT DEFAULT 'pending'`, `vi_path TEXT`,
  `translate_error TEXT`, `translated_at TEXT`, `translator TEXT`.
- Truy vấn `pending_translations(novel_id)`: chương có `crawl_status='done'` và
  `translate_status IN ('pending','failed')`, sắp theo `idx`.
- Glossary: `library/<slug>/glossary.md`, mỗi dòng `Hán = Việt` (bỏ dòng trống/
  `#`); không có file thì `glossary=None`.

## CLI

```bash
crawl add <url>              # CHỈ crawl, không dịch
crawl translate <slug|id>    # dịch chương chưa dịch của truyện đã có
    [--provider claude|lmstudio|ollama|openai]
    [--model <name>] [--base-url <url>]
    [--limit N]              # giới hạn số chương (thử trước)
    [--retranslate]          # dịch lại cả chương đã done
crawl list                   # thêm cột "đã dịch X/Y"
```

Điều kiện dịch một chương: `crawl_status='done'` (đã có file `raw/`). `translate`
không tự crawl. Resume: chạy lại `translate` tiếp tục từ chương chưa dịch.

## Prompt + glossary

- **System prompt** (ổn định cho cả truyện): vai trò dịch giả Trung→Việt; giữ
  văn phong, giọng văn; **tên riêng/thuật ngữ theo glossary**; không thêm/bớt nội
  dung; giữ format; chỉ trả bản dịch. Có glossary thì chèn bảng `Hán = Việt`.
- **User message**: `Tiêu đề: <title>\n\n<nội dung raw>`.
- **Output**: dịch cả tiêu đề lẫn thân → `TranslatedChapter`. Vòng lặp ghi
  `# <title_vi>\n\n<text_vi>` vào `vi/`.
- Mỗi chương độc lập (không ngữ cảnh chương trước).

## Vòng lặp dịch & xử lý lỗi (`core/translator_loop.py`)

`translate_pending(translator, lib, library_dir, novel, glossary, *, limit=None, min_ratio=0.3, log, sleep)`:

1. Lấy `pending_translations`; nếu `limit` thì cắt.
2. Mỗi chương: đọc text từ `raw/` (theo `file_path`), gọi
   `translator.translate_chapter(title, text, glossary)`, retry tối đa 3 lần
   (SDK Anthropic tự retry 429/5xx; local retry thủ công có backoff).
   - Kết quả rỗng hoặc quá ngắn (`len(text_vi) < min_ratio * len(text)`) → coi là
     lỗi, KHÔNG ghi file.
   - Thành công → `write_chapter(..., "vi", idx, title_vi, text_vi)`, cập nhật DB
     `translate_status='done'`, `vi_path`, `translator`, `translated_at`.
   - Thất bại → `translate_status='failed'`, `translate_error`.
3. `TranslateError` khi tạo/gọi backend (LM Studio chưa bật, thiếu key, base_url
   sai) → dừng sớm, `ClickException` thân thiện (gợi ý kiểm tra provider/endpoint).
4. Cuối lượt: in `X dịch OK, Y lỗi` + danh sách chương lỗi.

## Kiểm thử

Không gọi LLM/mạng thật trong suite tự động.

- **`Translator` fake**: trả bản dịch giả tất định → test `translate_pending`
  (ghi `vi/`, cập nhật DB, resume bỏ qua done, `--limit`, chương rỗng→failed,
  chương chưa crawl→bỏ qua).
- **Migration**: mở DB cũ (không có cột dịch) → xác minh cột được thêm, dữ liệu
  cũ giữ nguyên, chạy lại idempotent.
- **registry/preset**: `build_translator('ollama')` điền đúng base_url; `claude`
  ra `AnthropicTranslator`; thiếu base_url cho `openai` → lỗi rõ ràng. Mock SDK,
  không gọi mạng.
- **glossary**: parse `glossary.md` đúng, bỏ dòng trống/`#`.
- **Smoke test thật (thủ công)**: dịch vài chương với LM Studio (hoặc Ollama) và
  với Claude; xác nhận `vi/` có văn bản tiếng Việt hợp lý.

## Dependency & triển khai

- Extra `[translate]`: `anthropic>=0.40`, `openai>=1.40`. Cài khi cần dịch:
  `pip install -e '.[translate]'`. Crawler nền không đổi.
- README: mục "Dịch tiếng Việt" với 3 lối dùng (Claude / LM Studio / Ollama) và
  cách tạo `glossary.md`.
