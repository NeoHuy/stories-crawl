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

Chạy FlareSolverr rồi trỏ tool tới nó:

    docker run -d --name fs -p 8191:8191 --shm-size=1g \
      ghcr.io/flaresolverr/flaresolverr:latest
    STORIES_FLARESOLVERR_URL=http://localhost:8191 crawl add <url>

Hoặc dùng `docker-compose.yml` mẫu (service `app` + `flaresolverr`).

- Mặc định endpoint là `http://localhost:8191` (đổi bằng `STORIES_FLARESOLVERR_URL`).
- Cờ `--no-browser` tắt fallback: `crawl add --no-browser <url>`.
- FlareSolverr chạy trên Linux/Docker (kể cả server không màn hình). Tỉ lệ vượt
  Turnstile không đảm bảo 100%; chương không lấy được sẽ retry lần `update` sau.

## Hạn chế đã biết

- Chương có nội dung dưới 200 ký tự (ví dụ chỉ có lời tác giả) bị coi là
  tải lỗi và sẽ được thử lại ở mỗi lần `crawl update` — đây là ngưỡng
  chống chặn (anti-blocking heuristic) nên có thể tạo false positive với
  các chương thật sự ngắn.
- Với nguồn không bị chặn, `piaotia.com` đã được xác nhận hoạt động tốt ở
  chế độ nhanh; các nguồn bị Cloudflare cần FlareSolverr (xem mục trên).
