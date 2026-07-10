# Spec: Chế độ browser fallback vượt Cloudflare (FlareSolverr sidecar)

**Ngày:** 2026-07-10
**Trạng thái:** Đã duyệt thiết kế (sau spike so sánh)
**Liên quan:** mở rộng tool stories-crawl ([spec gốc](2026-07-08-stories-crawl-design.md))

## Mục đích

Cho phép tool tải được các nguồn bị Cloudflare/Turnstile chặn (ví dụ 69shuba)
khi chạy **trên server Linux + Docker** (tool là một phần của dự án web lưu trữ
truyện). Khi chế độ HTTP nhanh bị chặn, tool **tự động** gọi sang một service
FlareSolverr chạy container riêng để lấy HTML đã qua Cloudflare.

## Bối cảnh & spike đã kiểm chứng (2026-07-10)

**Tín hiệu bị chặn (đã kiểm chứng lại 2026-07-11):** khi gọi `scraper.get()`
trực tiếp thì Turnstile ném `CloudflareException`, NHƯNG khi đi qua
`crawler.read_novel()` của lncrawl thì KHÔNG — bộ giải của scraper nuốt challenge,
trả về trang "Just a moment" như thể thành công, parse ra rỗng → lncrawl ném
`AssertionError: No novel title` (hoặc trả 0 chương). Ở khâu tải chương, trang
bị chặn cho nội dung ngắn dưới ngưỡng `min_length` (triệu chứng đã thấy ở smoke
test Task 7). Vì vậy **fallback KHÔNG dựa vào bắt `CloudflareException`** mà dựa
vào **kết quả rỗng/thất bại** (xem "Cơ chế phát hiện" bên dưới).

Spike so sánh hai hướng trong container Linux arm64 trên 69shuba:

| Hướng | Kết quả | Thời gian |
|---|---|---|
| nodriver + Xvfb (nhúng vào image) | ✅ PASS, nội dung tiếng Trung sạch | ~6s |
| **FlareSolverr sidecar** (đã chọn) | ✅ PASS, nội dung tiếng Trung sạch | ~4s |

Chọn FlareSolverr vì cô lập toàn bộ Chrome+Xvfb vào một container chuyên dụng:
app image giữ nhẹ (không nhúng browser), crawler chỉ là HTTP client, browser
crash/restart độc lập không kéo sập app.

**Lưu ý trung thực về độ tin cậy:** lần spike FlareSolverr báo "Challenge not
detected" — không thực sự đối mặt một Turnstile cứng lần đó (Cloudflare thách
đố theo IP/xác suất). FlareSolverr dùng cùng công nghệ browser ẩn nên khả năng
tương đương, nhưng chưa có bằng chứng ép giải Turnstile cứng. Thiết kế coi việc
FlareSolverr thất bại một trang là **lỗi chương bình thường** (retry lần sau).

## Phạm vi

**Trong phạm vi:**
- `FlareSolverrClient`: HTTP client gọi FlareSolverr (`sessions.create`,
  `request.get`, `sessions.destroy`).
- Auto-fallback: chế độ nhanh cho kết quả rỗng/thất bại (xem "Cơ chế phát hiện")
  → chuyển cả truyện sang FlareSolverr và tải lại (DB resume bỏ qua chương `done`).
- Ghi đè khâu tải HTML của lncrawl (`get_soup`) để đi qua FlareSolverr, giữ
  nguyên logic parse của từng nguồn.
- Cờ `--no-browser` tắt hẳn fallback.
- Cấu hình endpoint FlareSolverr qua biến môi trường; docker-compose mẫu có
  sidecar.

**Ngoài phạm vi (YAGNI / giai đoạn sau):**
- Nhúng nodriver+Xvfb vào image (hướng A′ — đã loại sau spike).
- Nguồn cần POST/JSON qua browser (chỉ ghi đè `get_soup` cho nguồn HTML GET).
- Giải captcha tương tác cần click tay, residential proxy, Tor.
- Tích hợp sâu vào backend web (API/queue) — đây là spec riêng về sau; hiện tại
  crawler vẫn là CLI/thư viện, chỉ thêm khả năng gọi FlareSolverr.

## Kiến trúc

Mọi thao tác tải của lncrawl đi qua `crawler.get_soup(url)`; logic parse riêng
của từng nguồn (`read_novel_info`, `download_chapter_body`) gọi `get_soup` bên
trong. Chỉ cần **thay khâu tải HTML** bằng FlareSolverr, không đụng phần parse.

```
stories_crawl/
├── adapters/
│   ├── flaresolverr.py   # MỚI: FlareSolverrClient + FlareSolverrError
│   └── lncrawl_bridge.py # SỬA: nhận client, ghi đè get_soup, cho CloudflareException truyền lên
├── cli.py                # SỬA: cờ --no-browser, điều phối fallback, đọc config endpoint
docker-compose.yml        # MỚI (mẫu): dịch vụ app + sidecar flaresolverr
```

### `adapters/flaresolverr.py`

```python
class FlareSolverrError(Exception): ...   # service không tới được, hoặc trả lỗi/không giải được

class FlareSolverrClient:
    def __init__(self, endpoint: str, *, http=None, max_timeout_ms: int = 60000): ...
    #   endpoint ví dụ "http://flaresolverr:8191"; http là đối tượng gửi POST (inject để test)
    def __enter__(self) -> "FlareSolverrClient"   # tạo session (sessions.create), lưu session id
    def __exit__(self, *exc) -> None              # sessions.destroy (nuốt lỗi), đóng chắc chắn
    def fetch(self, url: str) -> str              # request.get qua session; trả HTML;
    #   lỗi mạng / status != ok / HTML còn dấu hiệu chặn → FlareSolverrError
```

- Dùng **một** session FlareSolverr cho cả lượt tải một truyện → tái dùng
  cookie `cf_clearance`, tránh giải lại mỗi chương.
- `fetch`: POST `{"cmd":"request.get","url":url,"session":sid,"maxTimeout":...}`;
  kiểm tra `status=="ok"` và HTML không còn `just a moment`/`cf-turnstile`/
  `challenge-platform`; nếu còn → `FlareSolverrError`.
- Đối tượng `http` (mặc định `requests`) được inject để test không cần service.

### `adapters/lncrawl_bridge.py` (sửa)

- `LncrawlAdapter(url, *, fetcher=None)`:
  - `fetcher=None` (mặc định): như hiện tại (chế độ nhanh).
  - `fetcher` là `FlareSolverrClient`: sau `init_crawler`, ghi đè trên
    **instance**: `crawler.get_soup = lambda u, *a, **k: crawler.make_soup(fetcher.fetch(u))`.

### Cơ chế phát hiện bị chặn

Fallback dựa vào **kết quả rỗng/thất bại**, không dựa vào exception Cloudflare:

- **Khâu mục lục:** coi là bị chặn nếu `get_novel_info` ném bất kỳ lỗi nào HOẶC
  trả về `NovelInfo` có 0 chương.
- **Khâu tải chương:** coi là bị chặn nếu lượt tải kết thúc với `done == 0` và
  `failed > 0` (mọi chương đều fail — dấu hiệu trang chương bị chặn hàng loạt).

Không xử lý trường hợp "mục lục qua nhưng một phần chương bị chặn" ở giai đoạn
này (YAGNI; 69shuba chặn cả trang mục lục nên trigger mục lục đã bắt được). Ghi
nhận là hạn chế đã biết.

### `cli.py` (sửa) — điều phối fallback

`_crawl` thêm tham số `allow_browser: bool` và đọc endpoint từ env
`STORIES_FLARESOLVERR_URL` (mặc định `http://localhost:8191`). Thêm cờ nội bộ để
tránh lặp vô hạn (đã ở chế độ browser thì không fallback nữa):

1. Thử chế độ nhanh (`LncrawlAdapter(url)`), tải như hiện tại.
2. Nếu phát hiện bị chặn (theo "Cơ chế phát hiện" — mục lục lỗi/0 chương, hoặc
   lượt tải `done==0 & failed>0`):
   - `allow_browser` False (do `--no-browser`) → `ClickException` thân thiện, dừng.
   - Ngược lại: đóng adapter nhanh; mở `FlareSolverrClient(endpoint)`; tạo
     `LncrawlAdapter(url, fetcher=client)`; chạy lại `_crawl` ở chế độ browser
     (DB resume bỏ qua chương `done`). Thông báo: "Trang có vẻ bị chặn — chuyển
     sang FlareSolverr".
3. `FlareSolverrError` khi tạo session (service không tới được) →
   `ClickException` gợi ý kiểm tra `STORIES_FLARESOLVERR_URL` / container.
4. `FlareSolverrError` trên một chương → chương tính là lỗi như bình thường,
   báo cuối lượt.

Cờ: `crawl add [--no-browser] <url>`, `crawl update [--no-browser] <key>`.

### `docker-compose.yml` (mẫu)

Hai service: `app` (crawler, chạy CLI/worker) và `flaresolverr`
(`ghcr.io/flaresolverr/flaresolverr:latest`, cổng 8191, `shm_size: 1g`). App
đặt `STORIES_FLARESOLVERR_URL=http://flaresolverr:8191`. Cung cấp mẫu để tích
hợp vào dự án web; không bắt buộc dùng đúng file này.

## Xử lý lỗi (tóm tắt)

| Tình huống | Xử lý |
|---|---|
| Chế độ nhanh cho kết quả rỗng/thất bại, `--no-browser` bật | `ClickException`: gợi ý bỏ `--no-browser` |
| FlareSolverr không tới được (tạo session lỗi) | `FlareSolverrError` → `ClickException` kiểm tra URL/container |
| FlareSolverr không giải được một trang | HTML còn dấu chặn → `FlareSolverrError` → chương failed, retry lần sau |
| Lỗi giữa chừng | `FlareSolverrClient.__exit__` luôn `sessions.destroy`, không để session rác |

## Kiểm thử

Không gọi FlareSolverr thật trong suite tự động (cần container + mạng).

- **`FlareSolverrClient`**: inject `http` giả trả JSON theo kịch bản → test
  `fetch` bóc HTML khi `status=ok`; ném `FlareSolverrError` khi status lỗi,
  khi HTML còn "Just a moment", khi `http` ném lỗi mạng. Test `__enter__/__exit__`
  gọi đúng `sessions.create`/`sessions.destroy` và destroy luôn chạy khi lỗi.
- **Ghi đè `get_soup`**: với `fetcher` truyền vào, xác minh `crawler.get_soup(u)`
  gọi `fetcher.fetch(u)` rồi `make_soup`, không chạm `scraper`.
- **Điều phối fallback (cli)**: fake adapter cho kết quả rỗng (get_novel_info
  lỗi, hoặc 0 chương, hoặc mọi chương fail) ở chế độ nhanh → xác minh CLI mở
  `FlareSolverrClient` (mock) và tải lại thành công; với `--no-browser` → dừng
  với thông báo, không mở client. Kiểm tra không lặp vô hạn (browser mode fail
  → không fallback tiếp).
- **Smoke test thật (thủ công)**: chạy FlareSolverr container + `crawl add
  <url 69shuba>`, xác nhận tải được vài chương nội dung sạch. Không đưa vào suite.

## Dependency & triển khai

- Python: dùng `requests` (đã có sẵn qua lncrawl) làm HTTP client — không thêm
  dependency mới vào crawler.
- Runtime: cần một container FlareSolverr chạy cạnh (sidecar). README + compose
  mẫu hướng dẫn. FlareSolverr image hỗ trợ arm64 và amd64 (đã kiểm chứng arm64).
- Không cần Chrome/Xvfb trong image app.
