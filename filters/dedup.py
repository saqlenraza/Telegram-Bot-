"""
CourseDrop Bot — Deduplication Filter
SQLite-based duplicate checker. Ensures the same course
is never posted to the Telegram channel twice.
"""

from db.database import Database


class DedupFilter:

    def __init__(self, db: Database):
        self.db = db

    def is_duplicate(self, course_id: str) -> bool:
        """Return True if this course was already posted (is a duplicate)."""
        return self.db.is_posted(course_id)

    def mark_posted(self, course: dict):
        """Mark a course as posted in the database."""
        self.db.mark_posted(course)

    def filter_new(self, courses: list[dict]) -> list[dict]:
        """Return only courses that have NOT been posted yet."""
        new_courses = []
        for course in courses:
            if not self.is_duplicate(course["id"]):
                new_courses.append(course)
        return new_courses
