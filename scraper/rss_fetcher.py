"""
CourseDrop Bot — RSS Fetcher
Core scraper. Uses feedparser to parse RSS. Extracts Udemy link
using regex from entry summary HTML.
"""

import feedparser
import re
from bs4 import BeautifulSoup

UDEMY_URL_PATTERN = re.compile(
    r'https?://(?:www\.)?udemy\.com/course/[\w-]+/?(?:\?[^\s"\'<>]*)?'
)


class RSSFetcher:

    def fetch_all(self, feeds: list) -> list:
        """Fetch from all RSS sources. Returns flat list of course dicts."""
        all_courses = []
        for feed_cfg in feeds:
            courses = self._fetch_one(feed_cfg["url"], feed_cfg["name"])
            all_courses.extend(courses)
            print(f"[{feed_cfg['name']}] Fetched {len(courses)} entries")
        return all_courses

    def _fetch_one(self, url: str, source: str) -> list:
        courses = []
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                course = self._parse_entry(entry, source)
                if course:
                    courses.append(course)
        except Exception as e:
            print(f"[{source}] ERROR: {e}")
        return courses

    def _parse_entry(self, entry, source: str) -> dict | None:
        title      = entry.get("title", "").strip()
        entry_id   = entry.get("id", entry.get("link", ""))
        source_url = entry.get("link", "")
        summary    = entry.get("summary", "")

        if not title or not entry_id:
            return None

        # Extract Udemy coupon URL from summary HTML
        udemy_url = self._extract_udemy_url(summary + " " + source_url)
        if not udemy_url:
            udemy_url = source_url  # fallback to coupon site page

        # Get category from tags — never return None
        tags     = entry.get("tags", [])
        category = "Course"
        if tags:
            term = tags[0].get("term")
            if term:
                category = term

        return {
            "id":         entry_id,
            "title":      title,
            "udemy_url":  udemy_url,
            "source_url": source_url,
            "source":     source,
            "category":   category,
        }

    def _extract_udemy_url(self, text: str) -> str | None:
        # First try direct regex on raw text
        match = UDEMY_URL_PATTERN.search(text)
        if match:
            return match.group(0)
        # Try parsing as HTML
        try:
            soup = BeautifulSoup(text, "lxml")
            for a in soup.find_all("a", href=True):
                if "udemy.com/course" in a["href"]:
                    return a["href"]
        except Exception:
            pass
        return None
