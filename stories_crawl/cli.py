import os
from pathlib import Path

import click

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


def _crawl(lib: Library, lib_dir: Path, url: str, existing=None):
    adapter_cls = registry.find_adapter_class(url)
    adapter = adapter_cls(url)
    try:
        click.echo(f"Đang lấy mục lục: {url}")
        info = adapter.get_novel_info(url)
        row = existing or lib.get_novel_by_url(url)
        if row is None:
            slug = make_slug(info.title, lib.existing_slugs())
            lib.create_novel(slug, info.title, info.author, url, adapter_cls.name)
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
    finally:
        adapter.close()


@main.command()
@click.argument("url")
def add(url):
    """Thêm truyện mới vào kho và tải toàn bộ chương."""
    lib_dir = _library_dir()
    lib = Library(lib_dir / "library.db")
    try:
        _crawl(lib, lib_dir, url)
    finally:
        lib.close()


@main.command()
@click.argument("key")
def update(key):
    """Tải các chương mới/còn thiếu của truyện đã có (theo slug hoặc id)."""
    lib_dir = _library_dir()
    lib = Library(lib_dir / "library.db")
    try:
        row = lib.get_novel(key)
        if row is None:
            raise click.ClickException(f"Không tìm thấy truyện: {key}")
        _crawl(lib, lib_dir, row["source_url"], existing=row)
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
