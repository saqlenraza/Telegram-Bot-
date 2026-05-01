"""
CourseDrop Bot — Courson.xyz Scraper
Scrapes courson.xyz for free Udemy courses with coupon codes.
Replaces Telegram channel monitoring (Telethon) which couldn't
resolve JavaScript-based courson.xyz redirect links.

Flow: courson.xyz/coupons → parse course cards → visit each
courson.xyz/coupon/ detail page → extract direct Udemy coupon URL
→ filter by rating and uses_left → return course dicts.
"""

import re
import time
import httpx
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; "
                  "Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,"
              "application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# ── Smart Filters ──────────────────────────────────────────────────────
MIN_RATING  = 4.3   # Skip courses rated below this
MIN_USES    = 1     # Skip courses with 0 uses left


class CoursonScraper:

    COUPONS_URL = "https://courson.xyz/coupons"

    def fetch_courses(self, pages: int = 2) -> list:
        """Scrape courson.xyz coupon pages and return list of course dicts.

        Each page is scraped for course cards, then each card's detail page
        is visited to extract the direct Udemy coupon URL.

        A 1-second delay is added between detail page fetches to avoid
        hammering courson.xyz too fast.
        """
        all_courses = []
        for page in range(1, pages + 1):
            url = f"{self.COUPONS_URL}?page={page}"
            courses = self._scrape_page(url)
            all_courses.extend(courses)
            print(f"[Courson] Page {page}: {len(courses)} courses found")
        return all_courses

    def _scrape_page(self, url: str) -> list:
        """Fetch a courson.xyz coupons page and parse course cards."""
        try:
            resp = httpx.get(
                url, headers=HEADERS,
                timeout=20, follow_redirects=True
            )
            if resp.status_code != 200:
                print(f"[Courson] HTTP {resp.status_code}")
                return []
            return self._parse_page(resp.text)
        except Exception as e:
            print(f"[Courson] Fetch error: {e}")
            return []

    def _parse_page(self, html: str) -> list:
        """Parse HTML of courson.xyz coupons page into course dicts."""
        soup = BeautifulSoup(html, "lxml")
        courses = []

        # Find all course links on the page
        # courson.xyz uses /coupon/ paths
        seen_urls = set()

        for a in soup.find_all("a", href=True):
            href = a["href"]

            # Build full URL
            if href.startswith("/coupon/"):
                href = f"https://courson.xyz{href}"

            # Only courson coupon pages
            if "courson.xyz/coupon/" not in href:
                continue

            # Remove UTM/query params
            href = href.split("?")[0]

            if href in seen_urls:
                continue
            seen_urls.add(href)

            # Get course details from card
            card = a.find_parent(
                ["div", "article", "li", "section"]
            )
            course = self._parse_card(card, href) if card else None

            if course:
                courses.append(course)

        return courses

    def _parse_card(self, card, courson_url: str) -> dict | None:
        """Parse a single course card element into a course dict.

        Extracts title, rating, uses_left, and category from the card HTML,
        then fetches the courson detail page to get the direct Udemy URL.

        Applies smart filters:
        - rating < 4.3 → skip
        - uses_left <= 0 → skip
        """
        try:
            # ── Title ────────────────────────────────────────────────
            title_el = card.find(["h2", "h3", "h4", "h5"])
            if not title_el:
                title_el = card.find(
                    class_=re.compile(r"title|name|heading", re.I)
                )
            title = title_el.get_text(strip=True) if title_el else ""
            if not title or len(title) < 5:
                return None

            card_text = card.get_text(" ", strip=True)

            # ── Rating — look for X.X pattern near "rating" ──────────
            rating = None
            rating_match = re.search(
                r"(\d\.\d)\s*(?:⭐|★|stars?|rating)",
                card_text, re.IGNORECASE
            )
            if not rating_match:
                rating_match = re.search(
                    r"(?:rating|rated?)[:\s]+(\d\.\d)",
                    card_text, re.IGNORECASE
                )
            if rating_match:
                rating = float(rating_match.group(1))

            # ── Smart Filter: rating too low → skip ──────────────────
            if rating is not None and rating < MIN_RATING:
                print(f"  ⏭️ Skipped (rating {rating} < {MIN_RATING}): {title[:50]}")
                return None

            # ── Coupon uses left ─────────────────────────────────────
            uses_left = None
            uses_match = re.search(
                r"(\d+)\s*coupon\s*uses?\s*left",
                card_text, re.IGNORECASE
            )
            if uses_match:
                uses_left = int(uses_match.group(1))

            # ── Smart Filter: 0 uses left → skip ─────────────────────
            if uses_left is not None and uses_left <= 0:
                print(f"  ⏭️ Skipped (0 uses left): {title[:50]}")
                return None

            # ── Category from hashtag ────────────────────────────────
            category = "Course"
            cat_match = re.search(r"#([a-zA-Z_]+)", card_text)
            if cat_match:
                category = cat_match.group(1).replace("_", " ").title()

            # ── Get real Udemy URL by fetching courson detail page ───
            # Add 1-second delay to avoid hitting courson.xyz too fast
            time.sleep(1)

            udemy_url = self._get_udemy_url(courson_url)
            if not udemy_url:
                return None

            course_id = re.sub(
                r"[^a-z0-9]", "-",
                courson_url.split("/")[-1].lower()
            )

            return {
                "id":             course_id,
                "title":          title,
                "udemy_url":      udemy_url,
                "source_url":     courson_url,
                "source":         "Courson",
                "category":       category,
                "rating":         str(rating) if rating else None,
                "uses_left":      uses_left,
                "image_url":      None,
                "original_price": None,
                "students":       None,
            }

        except Exception as e:
            print(f"[Courson] Card error: {e}")
            return None

    def _get_udemy_url(self, courson_detail_url: str) -> str | None:
        """Fetch courson detail page and extract direct Udemy coupon URL.

        courson.xyz detail pages have a redirect button that goes to:
            udemy.com/course/xyz/?couponCode=ABC

        Looks for the URL in three places:
        1. Regex search for udemy.com/course/ with couponCode in raw HTML
        2. BeautifulSoup <a href> tags containing udemy.com + couponCode
        3. JavaScript string literals containing the Udemy coupon URL

        Returns the Udemy coupon URL, or None if not found.
        """
        try:
            resp = httpx.get(
                courson_detail_url,
                headers=HEADERS,
                timeout=15,
                follow_redirects=True
            )
            if resp.status_code != 200:
                return None

            html = resp.text

            # Method 1: Direct regex match in HTML
            UDEMY_PATTERN = re.compile(
                r'https?://(?:www\.)?udemy\.com'
                r'/course/[a-zA-Z0-9_-]+'
                r'/?\?[^"\'<>\s]*couponCode='
                r'[^"\'<>\s]+'
            )
            match = UDEMY_PATTERN.search(html)
            if match:
                return match.group(0).rstrip("\"'/")

            # Method 2: BeautifulSoup <a> tag href search
            soup = BeautifulSoup(html, "lxml")
            for a in soup.find_all("a", href=True):
                if ("udemy.com/course/" in a["href"]
                        and "couponCode=" in a["href"]):
                    return a["href"]

            # Method 3: JavaScript string literals
            js_match = re.search(
                r'["\']('
                r'https?://(?:www\.)?udemy\.com'
                r'/course/[a-zA-Z0-9_-]+'
                r'/?\?[^"\']*couponCode=[^"\']+)'
                r'["\']',
                html
            )
            if js_match:
                return js_match.group(1)

            # No coupon URL found — skip this course
            print(f"  ⏭️ No Udemy coupon found: {courson_detail_url}")
            return None

        except Exception as e:
            print(f"[Courson] URL fetch error: {e}")
            return None
