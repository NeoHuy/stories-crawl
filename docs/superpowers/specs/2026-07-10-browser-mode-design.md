# Spec: Chế độ browser (auto-fallback vượt Cloudflare/Turnstile)

**Ngày:** 2026-07-10
**Trạng thái:** Đã duyệt thiết kế
**Liên quan:** mở rộng tool stories-crawl ([spec gốc](2026-07-08-stories-crawl-design.md))

## Mục đích

Cho phép tool tải được các nguồn bị Cloudflare/Turnstile chặn (ví dụ 69shuba),
bằng cách render trang qua một trình duyệt thật (nodriver headful) thay cho
HTTP thường khi chế độ nhanh bị chặn. Kích hoạt **tự động** (fallback), người
dùng không cần biết trước trang nào bị chặn.

## Bối cảnh đã kiểm chứng (spike 2026-07-10)

Thử thực tế trên 69shuba (trang dùng Cloudflare Turnstile):

| Cách | Kết quả |
|---|---|
| Chế độ nhanh (bộ giải tích hợp của `scraper`) | ❌ Ném `CloudflareException` — Turnstile cần captcha provider |
| nodriver **headless** | ❌ Kẹt "Just a moment" 42s, bị phát hiện |
| nodriver **headful** (cửa sổ Chrome hiện) | ✅ Qua trong ~7.5s tự động, lấy nội dung tiếng Trung sạch |

Kết luận nền cho thiết kế: browser vượt được, nhưng **bắt buộc headful** và
**cần phiên GUI**.

## Phạm vi

**Trong phạm vi:**
- Auto-fallback: chế độ nhanh gặp `CloudflareException` → chuyển cả truyện sang
  chế độ browser và tải lại (resume bỏ qua chương đã lưu nhờ DB).
- Cờ `--no-browser` trên `add`/`update` để tắt hẳn fallback (chỉ chạy chế độ nhanh).
- Một `BrowserSession` (nodriver headful) dùng chung cho cả lượt tải một truyện.
- Ghi đè khâu tải HTML của lncrawl, giữ nguyên logic parse của từng nguồn.

**Ngoài phạm vi (YAGNI / giai đoạn sau):**
- Hướng B "lấy vé một lần" (harvest `cf_clearance` rồi tải bằng HTTP nhanh) —
  chỉ làm nếu tốc độ thành vấn đề.
- Chế độ headless / chạy trên server không màn hình — Turnstile không cho.
- Giải captcha tương tác cần click tay, residential proxy, Tor.
- Cờ ép browser ngay từ đầu (`--browser`) — auto-fallback đã đủ.

## Kiến trúc

Mọi thao tác tải của lncrawl đi qua `crawler.get_soup(url)` →
`crawler.scraper.get(...)`; logic parse riêng của từng nguồn
(`read_novel_info`, `download_chapter_body`) gọi `get_soup` bên trong. Vì vậy
chỉ cần **thay khâu tải HTML**, không đụng phần parse.

```
stories_crawl/
├── adapters/
│   ├── browser.py        # MỚI: BrowserSession + lỗi BrowserBlockedError/BrowserUnavailableError
│   └── lncrawl_bridge.py # SỬA: nhận cờ browser, ghi đè get_soup, bắt CloudflareException
├── core/
│   └── registry.py       # (không đổi)
└── cli.py                # SỬA: cờ --no-browser, điều phối fallback
```

### `adapters/browser.py`

```python
class BrowserBlockedError(Exception): ...      # điều hướng xong nhưng không qua được challenge trong thời gian chờ
class BrowserUnavailableError(Exception): ...   # không khởi chạy được Chrome (thiếu GUI/Chrome)

class BrowserSession:
    def __init__(self, *, timeout: float = 45.0, poll: float = 5.0): ...
    def __enter__(self) -> "BrowserSession"          # khởi chạy nodriver headful; lỗi → BrowserUnavailableError
    def __exit__(self, *exc) -> None                 # luôn browser.stop() (đóng chắc chắn)
    def fetch(self, url: str) -> str                 # điều hướng, chờ Cloudflare qua, trả HTML; quá timeout → BrowserBlockedError
```

- Sở hữu **một** Chrome headful, tái dùng cho mọi trang trong lượt tải.
- `fetch`: điều hướng tới `url`, poll mỗi `poll` giây tới `timeout`. "Đã qua" =
  tiêu đề/HTML hết dấu hiệu chặn (`just a moment`, `cf-turnstile`,
  `challenge-platform`) **và** có nội dung thực (ngưỡng độ dài tối thiểu).
- Logic "poll tới khi hết chặn" tách khỏi việc lái Chrome để test được: hàm
  điều hướng thực tế là một seam có thể inject (fetcher giả trong test).

### `adapters/lncrawl_bridge.py` (sửa)

- `LncrawlAdapter(url, *, browser: bool = False, browser_session=None)`:
  - `browser=False` (mặc định): như hiện tại.
  - `browser=True`: sau khi `init_crawler`, ghi đè trên **instance**:
    `crawler.get_soup = lambda u, *a, **k: crawler.make_soup(session.fetch(u))`
    (và `get_response`/`post_soup` tương tự nếu nguồn HTML cần — tối thiểu là
    `get_soup`). `session` là `BrowserSession` được truyền vào.
- `supports()` không đổi.
- Nhận diện bị chặn: cho `CloudflareException` của `scraper` truyền lên nguyên
  vẹn (không bọc thành lỗi khác) để tầng điều phối bắt được.

### `cli.py` (sửa) — điều phối fallback

Trong `_crawl` (hàm dùng chung của `add`/`update`), thêm tham số `allow_browser: bool`:

1. Thử chế độ nhanh (`LncrawlAdapter(url)`), tải như hiện tại.
2. Nếu `get_novel_info` hoặc vòng tải ném `CloudflareException`:
   - Nếu `allow_browser` False (do `--no-browser`) → báo lỗi thân thiện, dừng.
   - Ngược lại: đóng adapter nhanh; mở `BrowserSession`; tạo
     `LncrawlAdapter(url, browser=True, browser_session=session)`; tải lại
     (DB resume bỏ qua chương đã `done`). Thông báo cho người dùng "Trang bị
     chặn — chuyển sang chế độ trình duyệt (một cửa sổ Chrome sẽ mở)".
3. `BrowserUnavailableError` → `click.ClickException` gợi ý cần môi trường có màn hình.
4. `BrowserBlockedError` xuyên suốt (không qua được) → chương/truyện tính là lỗi
   như bình thường, báo cuối lượt.

Cờ: `crawl add [--no-browser] <url>`, `crawl update [--no-browser] <key>`.

## Xử lý lỗi (tóm tắt)

| Tình huống | Xử lý |
|---|---|
| Chế độ nhanh gặp Cloudflare, `--no-browser` bật | `ClickException`: gợi ý bỏ `--no-browser` để dùng trình duyệt |
| Chrome không khởi chạy được (không GUI) | `BrowserUnavailableError` → `ClickException` thân thiện |
| Qua timeout vẫn "Just a moment" | `BrowserBlockedError` → chương failed, retry lần update sau |
| Lỗi giữa chừng | `BrowserSession.__exit__` luôn `browser.stop()`, không để Chrome mồ côi |

## Kiểm thử

Không chạy Chrome thật trong suite tự động (chậm, cần mạng + GUI).

- **`BrowserSession`**: inject fetcher giả trả HTML theo kịch bản (lần 1
  "Just a moment", lần sau nội dung thật) → test vòng chờ, phát hiện "đã qua",
  và timeout → `BrowserBlockedError`. Test `__exit__` luôn gọi stop.
- **Ghi đè `get_soup`**: với `browser=True`, xác minh `crawler.get_soup(u)` gọi
  `session.fetch(u)` rồi `make_soup`, không chạm `scraper`.
- **Điều phối fallback (cli)**: fake adapter ném `CloudflareException` ở chế độ
  nhanh → xác minh CLI mở BrowserSession (mock) và tải lại; với `--no-browser`
  → xác minh dừng với thông báo, không mở browser.
- **Smoke test thật (thủ công)**: `crawl add <url 69shuba>` → cửa sổ Chrome bật,
  qua Turnstile, tải được vài chương nội dung sạch. Không đưa vào suite.

## Dependency

Không thêm mới: `nodriver` đã được `lightnovel-crawler` kéo về; Chrome đã có sẵn
trên máy. README ghi rõ chế độ browser cần môi trường có màn hình (GUI).
