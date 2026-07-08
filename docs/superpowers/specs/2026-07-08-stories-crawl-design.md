# Spec: stories-crawl — Tool thu thập truyện tiếng Trung

**Ngày:** 2026-07-08
**Trạng thái:** Đã duyệt thiết kế

## Mục đích

CLI Python thu thập truyện từ các trang webnovel tiếng Trung, lưu vào kho dữ liệu
cá nhân dưới dạng file markdown + SQLite, phục vụ lưu trữ lâu dài. Pipeline dịch
sang tiếng Việt sẽ được bổ sung ở giai đoạn sau — thiết kế hiện tại phải chừa sẵn
chỗ cho nó nhưng KHÔNG triển khai phần dịch.

## Phạm vi

**Trong phạm vi:**
- CLI với 4 lệnh: `add`, `update`, `list`, `sources`.
- Tận dụng các source tiếng Trung có sẵn của `lightnovel-crawler` (~15 trang,
  gồm 69shuba, uukanshu, ixdzs...) thông qua một bridge adapter.
- Kiến trúc adapter cho phép viết adapter native cho trang mới về sau.
- Lưu nội dung chương thành file markdown, metadata/trạng thái vào SQLite.
- Resume: chạy lại lệnh là tải tiếp từ chỗ dừng.

**Ngoài phạm vi (giai đoạn sau):**
- Dịch sang tiếng Việt (chỉ chừa cấu trúc thư mục `raw/` → sau thêm `vi/`).
- Web UI, chạy nền tự động, xuất EPUB.
- Trang chống bot nặng (Qidian) — không hỗ trợ giai đoạn đầu.

## Kiến trúc

```
stories_crawl/
├── cli.py               # entry point, parse lệnh
├── core/
│   ├── downloader.py    # vòng lặp tải chương: delay, retry, cập nhật trạng thái
│   └── registry.py      # nhận diện domain URL → chọn adapter
├── adapters/
│   ├── base.py          # interface BaseAdapter
│   ├── lncrawl_bridge.py# bọc Crawler class của lightnovel-crawler
│   └── native/          # adapter tự viết (trống ở giai đoạn đầu)
└── storage/
    ├── db.py            # SQLite: schema, truy vấn novels/chapters
    └── files.py         # ghi file markdown, tạo slug thư mục
```

### Interface adapter (`base.py`)

```python
class BaseAdapter:
    def supports(url: str) -> bool          # domain này có xử lý được không
    def get_novel_info(url) -> NovelInfo    # tên, tác giả, danh sách chương (title, url, index)
    def get_chapter(chapter_url) -> str     # nội dung text sạch của 1 chương
```

`lncrawl_bridge.py` ánh xạ interface này sang API của lightnovel-crawler
(`read_novel_info()`, `download_chapter_body()`), duyệt danh sách source zh của
lncrawl để match domain. Nếu API nội bộ của lncrawl thay đổi, chỉ file bridge này
bị ảnh hưởng.

**Thứ tự chọn adapter:** native trước, lncrawl bridge sau.

## Lệnh CLI

```bash
crawl add <url>          # thêm truyện mới: lấy mục lục, tải toàn bộ chương
crawl update <slug|id>   # tải các chương mới/còn thiếu của truyện đã có
crawl list               # liệt kê truyện + tiến độ (đã tải / tổng chương)
crawl sources            # liệt kê domain được hỗ trợ
```

`add` với URL truyện đã tồn tại trong kho → hành xử như `update`.

## Kho lưu trữ

```
library/
├── library.db
└── <slug-truyện>/
    └── raw/
        ├── 0001-第一章.md
        └── 0002-第二章.md
```

- File markdown chỉ chứa: dòng đầu là `# <tiêu đề chương>`, sau đó là nội dung.
- Slug tạo từ tên truyện, giữ nguyên Hán tự (nhất quán với tên file chương),
  chỉ thay các ký tự không hợp lệ với filesystem (`/ \ : * ? " < > |`, khoảng
  trắng) bằng `-`; nếu trùng thì thêm hậu tố số (`-2`, `-3`...).
- Vị trí `library/` mặc định là `./library` tại thư mục làm việc, override bằng
  biến môi trường `STORIES_LIBRARY`.

### Schema SQLite

```sql
CREATE TABLE novels (
  id INTEGER PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  author TEXT,
  source_url TEXT UNIQUE NOT NULL,
  adapter TEXT NOT NULL,          -- tên adapter đã dùng
  status TEXT NOT NULL,           -- active | completed | error
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE chapters (
  id INTEGER PRIMARY KEY,
  novel_id INTEGER NOT NULL REFERENCES novels(id),
  idx INTEGER NOT NULL,           -- số thứ tự chương, bắt đầu từ 1
  title TEXT,
  source_url TEXT NOT NULL,
  file_path TEXT,                 -- đường dẫn tương đối từ library/, NULL nếu chưa tải
  crawl_status TEXT NOT NULL,     -- pending | done | failed
  error TEXT,                     -- thông báo lỗi lần tải gần nhất
  updated_at TEXT NOT NULL,
  UNIQUE(novel_id, idx)
);
```

Cột trạng thái dịch sẽ được thêm vào `chapters` ở giai đoạn sau (migration đơn giản).

## Luồng tải & xử lý lỗi

1. `add <url>` → registry chọn adapter → `get_novel_info()` → ghi novel + toàn bộ
   chapters (`pending`) vào DB trong 1 transaction.
2. Vòng lặp tải: lấy các chapter `pending`/`failed` theo thứ tự `idx`:
   - Delay 1–2 giây ngẫu nhiên giữa các chương.
   - Retry tối đa 3 lần với backoff khi lỗi mạng.
   - Nội dung rỗng hoặc < 200 ký tự → coi là bị chặn/lỗi, đánh dấu `failed`,
     KHÔNG ghi đè file cũ nếu có.
   - Thành công → ghi file, UPDATE chapter thành `done` (ghi file trước, update
     DB sau — nếu chết giữa chừng thì lần sau tải lại, ghi đè file là an toàn).
3. Kết thúc: in tổng kết (X done, Y failed) và liệt kê chương failed.
4. Ctrl-C hoặc đứt mạng giữa chừng → chạy lại `update` là tiếp tục, vì trạng thái
   nằm trong DB theo từng chương.

## Kiểm thử

- Unit test cho `storage/` (schema, resume query) và `core/registry.py` — dùng
  SQLite in-memory và fixture HTML tĩnh.
- Adapter test bằng fixture HTML lưu sẵn trong `tests/fixtures/` (không gọi mạng
  trong test).
- Smoke test thủ công với 1 truyện thật trên 69shuba khi hoàn thành.

## Dependency

- Python ≥ 3.10, `lightnovel-crawler` (pip), `click` cho CLI. SQLite dùng stdlib.
