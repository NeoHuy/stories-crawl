import os
from pathlib import Path

import click

from .adapters.base import UnsupportedSourceError
from .adapters.flaresolverr import FlareSolverrClient, FlareSolverrError
from .core import registry
from .core.downloader import download_pending
from .storage.db import Library
from .storage.files import make_slug

# test ghi đè để tắt sleep; runtime để trống dùng mặc định
DOWNLOAD_KWARGS: dict = {}


def _library_dir() -> Path:
    return Path(os.environ.get("STORIES_LIBRARY", "library"))


@click.group()
def main():
    """stories-crawl — thu thập truyện về kho cá nhân."""


def _looks_blocked(summary) -> bool:
    """Đoán một lượt tải có bị chặn (Cloudflare/JS) không, để kích hoạt fallback.

    Coi là bị chặn khi có lỗi VÀ số chương lỗi ít nhất bằng số chương tải được
    — bắt cả trường hợp tải được một phần rồi phần còn lại bị chặn, không chỉ
    khi 100% thất bại. Truyện chỉ có vài chương hỏng thật (lỗi ít so với thành
    công) thì không kích hoạt fallback nhầm.
    """
    return summary.failed > 0 and summary.failed >= summary.done


def _attempt_crawl(lib, lib_dir, url, existing, adapter):
    """Chạy một lượt tải với adapter đã tạo. Trả (blocked, row)."""
    click.echo(f"Đang lấy mục lục: {url}")
    try:
        info = adapter.get_novel_info(url)
    except Exception as e:
        click.echo(f"  (không lấy được mục lục: {e})")
        return True, None
    if not info.chapters:
        click.echo("  (mục lục rỗng)")
        return True, None
    row = existing or lib.get_novel_by_url(url)
    if row is None:
        slug = make_slug(info.title, lib.existing_slugs())
        lib.create_novel(slug, info.title, info.author, url, adapter.name)
        row = lib.get_novel_by_url(url)
    click.echo(f"{info.title} — {info.author} ({len(info.chapters)} chương)")
    new = lib.add_chapters(row["id"], info.chapters)
    if new:
        click.echo(f"{new} chương mới trong mục lục")
    summary = download_pending(
        adapter, lib, lib_dir, row, log=click.echo, **DOWNLOAD_KWARGS
    )
    click.echo(f"Hoàn tất: {summary.done} OK, {summary.failed} lỗi")
    for idx, title, err in summary.failures:
        click.echo(f"  - chương {idx} ({title}): {err}")
    return _looks_blocked(summary), row


def _crawl(lib, lib_dir, url, existing=None, *, allow_browser=True):
    try:
        adapter_cls = registry.find_adapter_class(url)
    except UnsupportedSourceError:
        raise click.ClickException(
            f"Nguồn không được hỗ trợ: {url} — xem 'crawl sources'"
        )

    adapter = adapter_cls(url)
    try:
        blocked, _ = _attempt_crawl(lib, lib_dir, url, existing, adapter)
    finally:
        adapter.close()
    if not blocked:
        return

    if not allow_browser:
        raise click.ClickException(
            "Trang có vẻ bị Cloudflare chặn. Bỏ cờ --no-browser để thử qua FlareSolverr."
        )

    click.echo("Trang có vẻ bị chặn — chuyển sang FlareSolverr...")
    endpoint = os.environ.get("STORIES_FLARESOLVERR_URL", "http://localhost:8191")
    try:
        with FlareSolverrClient(endpoint) as client:
            adapter = adapter_cls(url, fetcher=client)
            try:
                blocked2, _ = _attempt_crawl(lib, lib_dir, url, existing, adapter)
            finally:
                adapter.close()
    except FlareSolverrError as e:
        raise click.ClickException(
            f"Không dùng được FlareSolverr ({endpoint}): {e}. "
            f"Kiểm tra container FlareSolverr và biến STORIES_FLARESOLVERR_URL."
        )
    if blocked2:
        raise click.ClickException(
            "Vẫn không tải được qua FlareSolverr — trang có thể chặn mạnh."
        )


@main.command()
@click.argument("url")
@click.option("--no-browser", is_flag=True,
              help="Tắt fallback FlareSolverr khi trang bị chặn.")
def add(url, no_browser):
    """Thêm truyện mới vào kho và tải toàn bộ chương."""
    lib_dir = _library_dir()
    lib = Library(lib_dir / "library.db")
    try:
        _crawl(lib, lib_dir, url, allow_browser=not no_browser)
    finally:
        lib.close()


@main.command()
@click.argument("key")
@click.option("--no-browser", is_flag=True,
              help="Tắt fallback FlareSolverr khi trang bị chặn.")
def update(key, no_browser):
    """Tải các chương mới/còn thiếu của truyện đã có (theo slug hoặc id)."""
    lib_dir = _library_dir()
    lib = Library(lib_dir / "library.db")
    try:
        row = lib.get_novel(key)
        if row is None:
            raise click.ClickException(f"Không tìm thấy truyện: {key}")
        _crawl(lib, lib_dir, row["source_url"], existing=row,
               allow_browser=not no_browser)
    finally:
        lib.close()


@main.command("list")
def list_cmd():
    """Liệt kê truyện trong kho kèm tiến độ."""
    lib_dir = _library_dir()
    lib = Library(lib_dir / "library.db")
    try:
        rows = lib.list_novels()
        if not rows:
            click.echo("Kho trống.")
            return
        for r in rows:
            click.echo(
                f"[{r['id']}] {r['title']} ({r['slug']})"
                f" — {r['done_count']}/{r['total_count']} chương — {r['status']}"
            )
    finally:
        lib.close()


@main.command()
def sources():
    """Liệt kê các domain tiếng Trung được hỗ trợ."""
    from .adapters import lncrawl_bridge

    for domain in lncrawl_bridge.list_supported_domains():
        click.echo(domain)
