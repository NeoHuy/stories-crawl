# stories-crawl

CLI thu thập truyện tiếng Trung về kho cá nhân, lưu dạng markdown + SQLite.
Dùng [lightnovel-crawler](https://github.com/dipu-bd/lightnovel-crawler) làm
engine cho ~24 trang nguồn tiếng Trung (69shuba, ixdzs, piaotian...).

## Cài đặt

    python3 -m venv .venv
    .venv/bin/pip install -e .

## Sử dụng

    crawl sources                # các domain được hỗ trợ
    crawl add <url-trang-truyện> # tải truyện mới về kho
    crawl update <slug|id>       # tải tiếp chương mới/chương lỗi
    crawl list                   # danh sách truyện + tiến độ

Kho mặc định là `./library` (đổi bằng biến môi trường `STORIES_LIBRARY`):

    library/
    ├── library.db               # metadata + trạng thái từng chương
    └── <tên-truyện>/raw/        # mỗi chương một file markdown

Đứt mạng/Ctrl-C giữa chừng: chạy lại `crawl update <slug>` để tiếp tục.
Lần chạy đầu tiên tool tải index nguồn của lightnovel-crawler từ GitHub nên
cần mạng và hơi lâu; các lần sau dùng cache.

## Phát triển

    .venv/bin/pip install -e '.[dev]'
    .venv/bin/pytest

Truyện dịch tiếng Việt: giai đoạn sau — file gốc nằm ở `raw/`, bản dịch sẽ
sinh vào `vi/` cạnh đó (xem docs/superpowers/specs/).

## Vượt Cloudflare (chế độ FlareSolverr)

Một số nguồn (69shuba, ixdzs8, bq99...) chặn bằng Cloudflare/Turnstile. Khi chế
độ tải nhanh cho kết quả rỗng, tool **tự động** thử lại qua một service
[FlareSolverr](https://github.com/FlareSolverr/FlareSolverr) chạy container riêng.

### Cách dùng khuyến nghị: docker compose (FlareSolverr luôn sẵn sàng)

Dựng cả tool lẫn FlareSolverr bằng `docker-compose.yml` đi kèm. FlareSolverr chạy
thường trực (có `restart: unless-stopped`) nên khi trang bị Cloudflare là có sẵn,
không phải bật tay:

    docker compose build app                 # dựng image tool (lần đầu)
    docker compose up -d flaresolverr         # bật sidecar một lần, để chạy nền
    docker compose run --rm app crawl add <url>
    docker compose run --rm app crawl list

Kho truyện gắn ra host, mặc định `./library` cạnh compose. Đặt kho ở nơi khác
(ví dụ ổ dữ liệu riêng) bằng biến `STORIES_LIBRARY_HOST`:

    STORIES_LIBRARY_HOST=/data/truyen docker compose run --rm app crawl add <url>

Tool tự trỏ tới FlareSolverr qua tên service `http://flaresolverr:8191`.

### Cách dùng thủ công (không đóng gói tool vào Docker)

Chạy `crawl` từ máy, chỉ bật FlareSolverr trong Docker:

    docker run -d --name fs -p 8191:8191 --shm-size=1g \
      ghcr.io/flaresolverr/flaresolverr:latest
    STORIES_FLARESOLVERR_URL=http://localhost:8191 crawl add <url>

### Ghi chú

- Mặc định endpoint là `http://localhost:8191` (đổi bằng `STORIES_FLARESOLVERR_URL`;
  trong compose đã đặt sẵn `http://flaresolverr:8191`).
- Cờ `--no-browser` tắt fallback: `crawl add --no-browser <url>`.
- FlareSolverr chạy trên Linux/Docker (kể cả server không màn hình). Tỉ lệ vượt
  Turnstile không đảm bảo 100%; chương không lấy được sẽ retry lần `update` sau.
- File do container (chạy root) ghi vào `./library` sẽ thuộc quyền root; nên chọn
  **một** cách dùng (compose HOẶC thủ công) cho mỗi kho để tránh lẫn quyền sở hữu.

## Dịch tiếng Việt (tùy chọn)

Dịch các chương đã tải sang tiếng Việt bằng LLM. Cài thêm:

    pip install -e '.[translate]'

Cấu hình một lần qua biến môi trường (khuyến nghị), rồi chỉ cần `crawl translate <slug>`:

    # Claude (nhúng API key của bạn)
    export STORIES_TRANSLATOR=claude
    export STORIES_TRANSLATE_MODEL=claude-opus-4-8
    export STORIES_TRANSLATE_API_KEY=sk-ant-...

    # hoặc OpenAI/ChatGPT
    export STORIES_TRANSLATOR=openai
    export STORIES_TRANSLATE_MODEL=gpt-4o
    export STORIES_TRANSLATE_API_KEY=sk-...

    # hoặc LLM local (LM Studio / Ollama) — không tốn phí
    export STORIES_TRANSLATOR=ollama          # hoặc lmstudio
    export STORIES_TRANSLATE_MODEL=qwen2.5

    crawl translate <slug>        # dịch chương chưa dịch (resume được)
    crawl translate <slug> --limit 5          # thử vài chương trước
    crawl translate <slug> --provider lmstudio --model <tên>  # ghi đè tạm

Bản dịch lưu ở `library/<slug>/vi/`. Đặt file `library/<slug>/glossary.md`
(mỗi dòng `Hán = Việt`) để giữ nhất quán tên riêng/thuật ngữ giữa các chương.

`crawl translate` là lệnh riêng — chạy `crawl add`/`update` không dịch gì.

## Hạn chế đã biết

- Chương có nội dung dưới 200 ký tự (ví dụ chỉ có lời tác giả) bị coi là
  tải lỗi và sẽ được thử lại ở mỗi lần `crawl update` — đây là ngưỡng
  chống chặn (anti-blocking heuristic) nên có thể tạo false positive với
  các chương thật sự ngắn.
- Với nguồn không bị chặn, `piaotia.com` đã được xác nhận hoạt động tốt ở
  chế độ nhanh; các nguồn bị Cloudflare cần FlareSolverr (xem mục trên).
