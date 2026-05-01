"""
CourseDrop Bot — Telegram Channel Web Scraper
Scrapes t.me/s/ public channel web previews for free Udemy courses.
No authentication needed — just httpx + BeautifulSoup.

Why t.me/s/?
- Telegram's own domain — never blocks cloud IPs (unlike coupon sites)
- Public channel previews accessible without login
- No Telethon / SESSION_STRING needed
- Messages often contain direct Udemy URLs with couponCode

Flow: t.me/s/channel → parse messages → extract Udemy coupon URLs
→ filter by rating → return course dicts.
"""

import re
import urllib.parse as up
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

# ── URL Patterns ──────────────────────────────────────────────────────
# Direct Udemy URL with coupon code (strongest signal — FREE course)
UDEMY_COUPON_PATTERN = re.compile(
    r'https?://(?:www\.)?udemy\.com/course/'
    r'[a-zA-Z0-9_-]+/?'
    r'\?[^"\'<>\s]*couponCode=[^"\'<>\s]+'
)

# Any Udemy course URL (might be paid — needs checking)
UDEMY_URL_PATTERN = re.compile(
    r'https?://(?:www\.)?udemy\.com/course/'
    r'[a-zA-Z0-9_-]+/?'
    r'(?:\?[^"\'<>\s]*)?'
)

# Price pattern
PRICE_PATTERN = re.compile(r'[\$£€][\d,]+\.?\d*')

# Rating patterns
RATING_PATTERN = re.compile(
    r'(?:rating[:\s]*|rated[:\s]*|stars?[:\s]*)?([4-5]\.\d)',
    re.IGNORECASE
)

# Prefixes to strip from titles
TITLE_PREFIXES = [
    'FREE:', 'Free:', '🎓', '📚', '100% OFF', '[100% OFF]',
    '🔥', '🆓', '✅', '⭐', '👉', '💯', '📢', '🎁',
    'Free Course:', 'FREE COURSE:', 'Udemy Free:',
    'Free Udemy Course:', '[Free]', '[FREE]',
]

# ── Smart Filters ──────────────────────────────────────────────────────
MIN_RATING = 4.3   # Skip courses rated below this


class TelegramWebScraper:
    """Scrapes free Udemy courses from Telegram channel web previews."""

    def __init__(self, channels: list[str]):
        self.channels = channels

    def fetch_courses(self, pages: int = 2) -> list:
        """Scrape all configured channels and return list of course dicts.

        Each channel's t.me/s/ preview page is fetched and parsed for
        messages containing Udemy coupon URLs. Multiple pages are
        scraped by using the 'before' parameter for older messages.
        """
        all_courses = []

        for channel in self.channels:
            try:
                courses = self._scrape_channel(channel, pages)
                all_courses.extend(courses)
                print(f"[TG-Web] @{channel}: {len(courses)} FREE courses found")
            except Exception as e:
                print(f"[TG-Web] @{channel} error: {e}")

        return all_courses

    def _scrape_channel(self, channel: str, pages: int = 2) -> list:
        """Scrape a single channel's t.me/s/ preview pages."""
        courses = []
        before_id = None

        for page in range(1, pages + 1):
            if before_id:
                url = f"https://t.me/s/{channel}?before={before_id}"
            else:
                url = f"https://t.me/s/{channel}"

            print(f"[TG-Web] Fetching: {url}")

            try:
                resp = httpx.get(
                    url, headers=HEADERS,
                    timeout=20, follow_redirects=True
                )
                print(f"[TG-Web] Response: {resp.status_code} | HTML length: {len(resp.text)}")

                if resp.status_code != 200:
                    print(f"[TG-Web] HTTP {resp.status_code} — skipping")
                    break

            except Exception as e:
                print(f"[TG-Web] Fetch error: {e}")
                break

            page_courses, last_msg_id = self._parse_page(resp.text, channel)
            courses.extend(page_courses)

            # Get oldest message ID for next page pagination
            if last_msg_id:
                before_id = last_msg_id
            else:
                break  # No more messages

        return courses

    def _parse_page(self, html: str, channel: str) -> tuple[list, int | None]:
        """Parse a t.me/s/ page and extract courses from messages.

        Returns (courses_list, oldest_message_id) tuple.
        The oldest message ID is used for pagination to fetch older messages.
        """
        soup = BeautifulSoup(html, "lxml")
        courses = []
        oldest_msg_id = None

        # t.me/s/ wraps each message in a div with class "message"
        messages = soup.find_all("div", class_="message")

        if not messages:
            # Fallback: try broader selector
            messages = soup.select("[data-post]")

        print(f"[TG-Web] Found {len(messages)} messages on page")

        for msg_div in messages:
            try:
                # Get message ID from data-post attribute (format: "channel/12345")
                data_post = msg_div.get("data-post", "")
                msg_id = None
                if "/" in data_post:
                    msg_id = int(data_post.split("/")[-1])
                    oldest_msg_id = msg_id

                # Get message text container
                text_div = msg_div.find("div", class_="text")
                if not text_div:
                    # Fallback: use the whole message div text
                    text_div = msg_div

                text = text_div.get_text(" ", strip=True)

                if not text or len(text) < 10:
                    continue

                # ── Try to find Udemy coupon URL ─────────────────────
                course = self._extract_course(text_div, text, channel, msg_id)
                if course:
                    courses.append(course)

            except Exception as e:
                print(f"[TG-Web] Message parse error: {e}")
                continue

        return courses, oldest_msg_id

    def _extract_course(
        self, text_div, text: str, channel: str, msg_id: int | None
    ) -> dict | None:
        """Extract a course dict from a Telegram message.

        Priority:
        1. Direct Udemy URL with couponCode → FREE course, use directly
        2. Direct Udemy URL without couponCode → likely PAID, skip
        3. No Udemy URL → skip
        """
        # ── Check for direct Udemy coupon URL ────────────────────────
        coupon_match = UDEMY_COUPON_PATTERN.search(str(text_div))
        if not coupon_match:
            # Also search in the plain text (sometimes URLs aren't in <a> tags)
            coupon_match = UDEMY_COUPON_PATTERN.search(text)

        if coupon_match:
            udemy_url = coupon_match.group(0).rstrip("\"'/")
            # Clean URL — keep only coupon params
            udemy_url = self._clean_udemy_url(udemy_url)
        else:
            # No coupon URL — check if there's any Udemy URL (paid link)
            any_udemy = UDEMY_URL_PATTERN.search(str(text_div))
            if not any_udemy:
                any_udemy = UDEMY_URL_PATTERN.search(text)

            if any_udemy:
                # Udemy URL exists but NO couponCode — paid course, skip
                return None
            else:
                # No Udemy URL at all — skip
                return None

        # ── Extract title ────────────────────────────────────────────
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        title = lines[0] if lines else "Free Course"

        # Clean common prefixes
        for prefix in TITLE_PREFIXES:
            if title.startswith(prefix):
                title = title.replace(prefix, '', 1).strip()

        # If title is a URL, try next line
        if title.startswith("http") and len(lines) > 1:
            title = lines[1]
            for prefix in TITLE_PREFIXES:
                if title.startswith(prefix):
                    title = title.replace(prefix, '', 1).strip()

        title = title[:200] or "Free Course"

        # ── Extract rating ───────────────────────────────────────────
        rating = self._extract_rating(text)

        # ── Smart Filter: rating too low → skip ──────────────────────
        if rating and float(rating) < MIN_RATING:
            print(f"  ⏭️ Skipped (rating {rating} < {MIN_RATING}): {title[:50]}")
            return None

        # ── Extract original price ───────────────────────────────────
        original_price = self._extract_price(text)

        # ── Build course ID ──────────────────────────────────────────
        entry_id = f"{channel}_{msg_id}" if msg_id else f"{channel}_{hash(title) % 100000}"

        # ── Extract image ────────────────────────────────────────────
        # t.me/s/ pages include message photos as <img> tags
        image_url = None
        img = text_div.find_parent("div", class_="message")
        if img:
            img_tag = img.find("img")
            if img_tag and img_tag.get("src"):
                image_url = img_tag["src"]

        return {
            "id":             entry_id,
            "title":          title,
            "udemy_url":      udemy_url,
            "source_url":     udemy_url,
            "source":         f"@{channel}",
            "category":       "Course",
            "image_url":      image_url,
            "original_price": original_price,
            "rating":         rating,
            "students":       None,
        }

    def _clean_udemy_url(self, url: str) -> str:
        """Clean a Udemy URL — remove tracking params, keep only coupon params."""
        try:
            parsed = up.urlparse(url)
            params = up.parse_qs(parsed.query)

            # Keep only coupon-related parameters
            clean_params = {}
            for key in ["couponCode", "coupon_code", "deal_code"]:
                if key in params:
                    clean_params[key] = params[key][0]

            if clean_params:
                query = up.urlencode(clean_params)
                clean_url = up.urlunparse((
                    parsed.scheme, parsed.netloc,
                    parsed.path, '', query, ''
                ))
            else:
                # No coupon params — strip all tracking
                clean_url = up.urlunparse((
                    parsed.scheme, parsed.netloc,
                    parsed.path, '', '', ''
                ))
            return clean_url
        except Exception:
            return url

    def _extract_price(self, text: str) -> str | None:
        """Extract original price from message text."""
        match = PRICE_PATTERN.search(text)
        if match:
            return match.group(0)
        return None

    def _extract_rating(self, text: str) -> str | None:
        """Extract course rating from message text."""
        match = RATING_PATTERN.search(text)
        if match:
            return match.group(1)

        # Fallback: standalone 4.X pattern
        simple = re.search(r'\b([4-5]\.\d)\b', text)
        if simple:
            return simple.group(1)

        return None
