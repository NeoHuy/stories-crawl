import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS novels (
  id INTEGER PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  author TEXT,
  source_url TEXT UNIQUE NOT NULL,
  adapter TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chapters (
  id INTEGER PRIMARY KEY,
  novel_id INTEGER NOT NULL REFERENCES novels(id),
  idx INTEGER NOT NULL,
  title TEXT,
  source_url TEXT NOT NULL,
  file_path TEXT,
  crawl_status TEXT NOT NULL,
  error TEXT,
  updated_at TEXT NOT NULL,
  UNIQUE(novel_id, idx)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Library:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        with self.conn:
            self.conn.executescript(SCHEMA)

    def close(self):
        self.conn.close()

    def create_novel(self, slug, title, author, source_url, adapter) -> int:
        now = _now()
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO novels"
                " (slug, title, author, source_url, adapter, status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, 'active', ?, ?)",
                (slug, title, author, source_url, adapter, now, now),
            )
        return cur.lastrowid

    def get_novel_by_url(self, url):
        return self.conn.execute(
            "SELECT * FROM novels WHERE source_url = ?", (url,)
        ).fetchone()

    def get_novel(self, key):
        if str(key).isdigit():
            row = self.conn.execute(
                "SELECT * FROM novels WHERE id = ?", (int(key),)
            ).fetchone()
            if row:
                return row
        return self.conn.execute(
            "SELECT * FROM novels WHERE slug = ?", (str(key),)
        ).fetchone()

    def existing_slugs(self) -> set:
        return {r["slug"] for r in self.conn.execute("SELECT slug FROM novels")}

    def add_chapters(self, novel_id, chapters) -> int:
        now = _now()
        inserted = 0
        with self.conn:
            for ch in chapters:
                cur = self.conn.execute(
                    "INSERT OR IGNORE INTO chapters"
                    " (novel_id, idx, title, source_url, crawl_status, updated_at)"
                    " VALUES (?, ?, ?, ?, 'pending', ?)",
                    (novel_id, ch.idx, ch.title, ch.url, now),
                )
                inserted += cur.rowcount
        return inserted

    def pending_chapters(self, novel_id):
        return self.conn.execute(
            "SELECT * FROM chapters"
            " WHERE novel_id = ? AND crawl_status IN ('pending', 'failed')"
            " ORDER BY idx",
            (novel_id,),
        ).fetchall()

    def mark_chapter_done(self, chapter_id, file_path):
        with self.conn:
            self.conn.execute(
                "UPDATE chapters SET crawl_status = 'done', file_path = ?,"
                " error = NULL, updated_at = ? WHERE id = ?",
                (file_path, _now(), chapter_id),
            )

    def mark_chapter_failed(self, chapter_id, error):
        with self.conn:
            self.conn.execute(
                "UPDATE chapters SET crawl_status = 'failed', error = ?,"
                " updated_at = ? WHERE id = ?",
                (error, _now(), chapter_id),
            )

    def touch_novel(self, novel_id):
        with self.conn:
            self.conn.execute(
                "UPDATE novels SET updated_at = ? WHERE id = ?", (_now(), novel_id)
            )

    def set_novel_status(self, novel_id, status):
        with self.conn:
            self.conn.execute(
                "UPDATE novels SET status = ?, updated_at = ? WHERE id = ?",
                (status, _now(), novel_id),
            )

    def list_novels(self):
        return self.conn.execute(
            "SELECT n.*,"
            " COUNT(c.id) AS total_count,"
            " COALESCE(SUM(CASE WHEN c.crawl_status = 'done' THEN 1 ELSE 0 END), 0)"
            "   AS done_count"
            " FROM novels n LEFT JOIN chapters c ON c.novel_id = n.id"
            " GROUP BY n.id ORDER BY n.updated_at DESC"
        ).fetchall()
