"""
CourseDrop Bot — RSS Fetcher
Core scraper. Uses feedparser to parse RSS. Extracts Udemy link,
image thumbnail, price, and rating from entry summary HTML.
"""

import feedparser
import re
from bs4 import BeautifulSoup

UDEMY_URL_PATTERN = re.compile(
    r'https?://(?:www\.)?udemy\.com/course/[\w-]+/?(?:\?[^\s"\'<>]*)?'
)

PRICE_PATTERN = re.compile(r'[\$£€][\d,]+\.?\d*')

RATING_PATTERN = re.compile(
    r'(?:rating[:\s]*|rated[:\s]*|stars?[:\s]*)?([4-5]\.\d)',
    re.IGNORECASE
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

        # Step 1: Extract Udemy coupon URL from summary HTML
        # (works for TutorialBar, CouponScorpion, RealDiscount etc.)
        udemy_url = self._extract_udemy_url(summary + " " + source_url)

        # Step 2: If not found AND source is Discudemy, fetch the
        # Discudemy page to extract the real Udemy URL from its HTML
        if not udemy_url and source == "Discudemy":
            udemy_url = self._fetch_udemy_url_from_page(source_url)

        # Step 3: If still no valid Udemy URL, skip this course entirely
        # Do NOT fallback to Discudemy URL — only direct Udemy links allowed
        if not udemy_url:
            return None

        # Get category from tags — never return None
        tags     = entry.get("tags", [])
        category = "Course"
        if tags:
            term = tags[0].get("term")
            if term:
                category = term

        # Extract image/thumbnail URL
        image_url = self._extract_image_url(entry, summary)

        # Extract original price from summary text
        original_price = self._extract_price(summary)

        # Extract rating from summary text
        rating = self._extract_rating(summary, title)

        return {
            "id":             entry_id,
            "title":          title,
            "udemy_url":      udemy_url,
            "source_url":     source_url,
            "source":         source,
            "category":       category,
            "image_url":      image_url,
            "original_price": original_price,
            "rating":         rating,
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

    def _fetch_udemy_url_from_page(self, page_url: str) -> str | None:
        """Fetch a coupon site page and extract the real Udemy course URL.

        Used for Discudemy whose RSS feed does not contain Udemy URLs
        in the summary — the actual udemy.com link is only on the page.
        """
        import httpx
        try:
            resp = httpx.get(
                page_url,
                timeout=10,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            match = UDEMY_URL_PATTERN.search(resp.text)
            return match.group(0) if match else None
        except Exception:
            return None

    def _extract_image_url(self, entry, summary: str) -> str | None:
        """Extract course thumbnail URL from RSS entry.

        Strategy:
        1. Check media_content (standard RSS media enclosure)
        2. Check media_thumbnail (RSS media thumbnail)
        3. Parse summary HTML for <img> tags
        4. Return None if no image found
        """
        # 1. media_content — most RSS feeds use this for featured images
        media_content = entry.get("media_content", [])
        if media_content:
            for media in media_content:
                url = media.get("url", "")
                if url and ("image" in media.get("type", "image") or url):
                    return url

        # 2. media_thumbnail
        media_thumbnail = entry.get("media_thumbnail", [])
        if media_thumbnail:
            for thumb in media_thumbnail:
                url = thumb.get("url", "")
                if url:
                    return url

        # 3. Parse summary HTML for <img> tags
        try:
            soup = BeautifulSoup(summary, "lxml")
            img = soup.find("img")
            if img and img.get("src"):
                return img["src"]
        except Exception:
            pass

        return None

    def _extract_price(self, summary: str) -> str | None:
        """Extract original price from summary text.

        Looks for patterns like $199.99, £49.99, €29.99
        Returns the first match or None.
        """
        match = PRICE_PATTERN.search(summary)
        if match:
            return match.group(0)
        return None

    def _extract_rating(self, summary: str, title: str) -> str | None:
        """Extract course rating from summary or title text.

        Looks for patterns like "4.6" near "rating" keyword,
        or standalone "4.X" ratings in the text.
        Returns the rating string (e.g. "4.6") or None.
        """
        # Try summary first — more likely to contain rating info
        text_to_search = summary + " " + title

        # Look for explicit "rating" mentions
        match = RATING_PATTERN.search(text_to_search)
        if match:
            return match.group(1)

        # Fallback: look for standalone 4.X pattern in summary
        # (many coupon sites include rating without "rating" keyword)
        simple_rating = re.search(r'\b([4-5]\.\d)\b', summary)
        if simple_rating:
            return simple_rating.group(1)

        return None
