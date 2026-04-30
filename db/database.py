"""
CourseDrop Bot — SQLite Database Handler
Tracks every posted coupon ID so no duplicate posts ever happen.
"""

import sqlite3
from config import DB_PATH, CLEANUP_DAYS


class Database:

    def __init__(self):
        self._setup()

    def _setup(self):
        """Create tables if they do not exist"""
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS posted_courses (
                    id         TEXT PRIMARY KEY,
                    title      TEXT,
                    source     TEXT,
                    posted_at  TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.commit()

    def is_posted(self, course_id: str) -> bool:
        """Return True if this course was already posted"""
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT id FROM posted_courses WHERE id = ?",
                (course_id,)
            ).fetchone()
        return row is not None

    def mark_posted(self, course: dict):
        """Save course as posted"""
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO posted_courses (id, title, source) VALUES (?, ?, ?)",
                (course["id"], course["title"], course["source"])
            )
            conn.commit()

    def cleanup_old(self):
        """Remove records older than CLEANUP_DAYS to keep DB small"""
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "DELETE FROM posted_courses WHERE posted_at < datetime('now', ?)",
                (f'-{CLEANUP_DAYS} days',)
            )
            conn.commit()
