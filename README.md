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

## Hạn chế đã biết

- Chương có nội dung dưới 200 ký tự (ví dụ chỉ có lời tác giả) bị coi là
  tải lỗi và sẽ được thử lại ở mỗi lần `crawl update` — đây là ngưỡng
  chống chặn (anti-blocking heuristic) nên có thể tạo false positive với
  các chương thật sự ngắn.
- Một số nguồn zh trong danh sách của lightnovel-crawler hiện đang bị chặn
  bởi Cloudflare/JS challenge (69shuba, ixdzs8, họ bq99...) nên `crawl add`
  sẽ thất bại với các nguồn này. Đã xác nhận `piaotia.com` hoạt động tốt.
