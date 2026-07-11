# Nguồn truyện tiếng Trung được hỗ trợ

Danh sách các trang nguồn tiếng Trung mà tool crawl được, lấy từ engine
[lightnovel-crawler](https://github.com/dipu-bd/lightnovel-crawler) (nhóm `sources/zh`).
Tổng cộng **24 domain** thuộc **12 họ trang** (mỗi họ dùng chung một bộ parse).

Xem danh sách trực tiếp (luôn cập nhật theo engine):

    crawl sources

> Ghi chú: đây là các nguồn *engine hỗ trợ*. Cột trạng thái bên dưới phản ánh
> những gì **đã kiểm chứng thực tế** trong quá trình phát triển — nguồn chưa kiểm
> không có nghĩa là hỏng, chỉ là chưa thử.

## Chú thích trạng thái

| Ký hiệu | Nghĩa |
|---|---|
| ✅ | Chạy tốt ở **chế độ nhanh** (không cần FlareSolverr) — đã kiểm |
| 🛡️ | Bị Cloudflare, **chạy được qua FlareSolverr** — đã kiểm |
| ⚠️ | Bị chặn ở chế độ nhanh (Cloudflare/JS) — **nhiều khả năng cần FlareSolverr**, chưa kiểm qua FlareSolverr |
| ❔ | Chưa kiểm chứng |

## Danh sách theo họ trang

| Họ trang (crawler) | Domain | Trạng thái |
|---|---|---|
| 69shuba | `69shuba.com` | 🛡️ |
| | `69shu.com` | ❔ (cùng họ, nhiều khả năng 🛡️) |
| | `69shu.pro` | ❔ (cùng họ, nhiều khả năng 🛡️) |
| | `69shuba.cx` | ❔ (cùng họ, nhiều khả năng 🛡️) |
| | `69shu.me` | ❔ (cùng họ, nhiều khả năng 🛡️) |
| piaotian | `piaotia.com` | ✅ |
| | `piaotian.com` | ❔ (cùng họ, nhiều khả năng ✅) |
| | `ptwxz.com` | ❔ (cùng họ, nhiều khả năng ✅) |
| ixdzs | `ixdzs8.com` | ⚠️ (JS challenge) |
| | `ixdzs8.tw` | ⚠️ |
| | `aixdzs.com` | ⚠️ |
| | `tw.m.ixdzs.com` | ⚠️ |
| shw5 | `shw5.cc` | ⚠️ (JS challenge) |
| | `bq99.cc` | ⚠️ |
| novel543 | `novel543.com` | ⚠️ (Cloudflare 403) |
| ddxsss | `ddtxt8.cc` | ⚠️ (JS challenge) |
| | `ddxss.cc` | ❔ |
| 27k | `lreads.com` | ❔ |
| | `tw.27k.net` | ❔ |
| powanjuan | `powanjuan.cc` | ❔ |
| shuhaige | `m.shuhaige.net` | ❔ |
| trxs | `trxs.cc` | ❔ |
| xbanxia | `xbanxia.com` | ❔ |
| | `banxia.cc` | ❔ |

## Cách dùng

Nguồn ✅ (chế độ nhanh) — chạy thẳng, không cần Docker:

    crawl add 'https://www.piaotia.com/bookinfo/...'

Nguồn 🛡️/⚠️ (bị Cloudflare) — cần FlareSolverr; tool tự động fallback:

    docker compose up -d flaresolverr
    STORIES_FLARESOLVERR_URL=http://localhost:8191 crawl add 'https://www.69shuba.com/book/...'

Xem thêm mục "Vượt Cloudflare" trong [README](../README.md).

## Ghi chú kỹ thuật

- Các domain "cùng họ" dùng chung một bộ parse của lncrawl, nên hành vi
  (kể cả bị chặn) thường giống nhau — nhưng cơ chế Cloudflare có thể khác nhau
  theo từng domain, vì vậy vẫn để ❔ tới khi kiểm chứng.
- Các nguồn ⚠️ bị chặn ở chế độ nhanh trong quá trình phát triển nhưng **chưa
  thử lại qua FlareSolverr** — khi cần, cứ chạy với FlareSolverr, tool sẽ tự
  fallback; nếu tải được thì nâng lên 🛡️.
- Nguồn tiếng khác (Anh, Việt, Nhật...) — engine hỗ trợ 300+ nguồn nhưng tool
  hiện chỉ liệt kê nhóm `zh`. Mở rộng sang ngôn ngữ khác để **phase sau**.
