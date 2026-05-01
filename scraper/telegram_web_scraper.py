"""
CourseDrop Bot — Telegram Channel Web Scraper
Scrapes t.me/s/ public channel web previews for free Udemy courses.
No authentication needed — just httpx + BeautifulSoup.

Why t.me/s/?
- Telegram's own domain — never blocks cloud IPs (unlike coupon sites)
- Public channel previews accessible without login
- No Telethon / SESSION_STRING needed

How it works:
1. Fetch t.me/s/channel public preview page
2. Parse each message — extract text, inline button links
3. Follow button links (bot links, short links, courson links)
4. Resolve to direct Udemy coupon URL (couponCode=)
5. Filter by rating >= 4.3
6. Return course dicts
"""

import re
import time
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
# Direct Udemy URL with coupon code
UDEMY_COUPON_PATTERN = re.compile(
    r'https?://(?:www\.)?udemy\.com/course/'
    r'[a-zA-Z0-9_-]+/?'
    r'\?[^"\'<>\s]*couponCode=[^"\'<>\s]+'
)

# Any Udemy course URL
UDEMY_URL_PATTERN = re.compile(
    r'https?://(?:www\.)?udemy\.com/course/'
    r'[a-zA-Z0-9_-]+/?'
    r'(?:\?[^"\'<>\s]*)?'
)

# Price pattern
PRICE_PATTERN = re.compile(r'[\$£€][\d,]+\.?\d*')

# Rating patterns — handles ⭐ 4.7, rated 4.6, etc.
RATING_PATTERN = re.compile(
    r'(?:⭐|★)?\s*([4-5]\.\d)\s*(?:⭐|★|\|)',
)

# Prefixes to strip from titles
TITLE_PREFIXES = [
    'FREE:', 'Free:', '🎓', '📚', '100% OFF', '[100% OFF]',
    '🔥', '🆓', '✅', '⭐', '👉', '💯', '📢', '🎁',
    'Free Course:', 'FREE COURSE:', 'Udemy Free:',
    'Free Udemy Course:', '[Free]', '[FREE]',
    '🔰',
]

# ── Smart Filters ──────────────────────────────────────────────────────
MIN_RATING = 4.3

# ── Rate limiting ──────────────────────────────────────────────────────
RESOLVE_DELAY = 1  # seconds between URL resolution requests


class TelegramWebScraper:
    """Scrapes free Udemy courses from Telegram channel web previews."""

    def __init__(self, channels: list[str]):
        self.channels = channels

    def fetch_courses(self, pages: int = 2) -> list:
        """Scrape all configured channels and return list of course dicts."""
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
                print(f"[TG-Web] Response: {resp.status_code} | HTML: {len(resp.text)}")

                if resp.status_code != 200:
                    print(f"[TG-Web] HTTP {resp.status_code} — skipping")
                    break

            except Exception as e:
                print(f"[TG-Web] Fetch error: {e}")
                break

            page_courses, last_msg_id = self._parse_page(resp.text, channel)
            courses.extend(page_courses)

            if last_msg_id:
                before_id = last_msg_id
            else:
                break

        return courses

    def _parse_page(self, html: str, channel: str) -> tuple[list, int | None]:
        """Parse a t.me/s/ page and extract courses from messages."""
        soup = BeautifulSoup(html, "lxml")
        courses = []
        oldest_msg_id = None

        # t.me/s/ uses class="tgme_widget_message" and data-post="channel/msgid"
        messages = soup.find_all(class_="tgme_widget_message")
        print(f"[TG-Web] Found {len(messages)} messages on page")

        for msg_div in messages:
            try:
                # Get message ID
                data_post = msg_div.get("data-post", "")
                msg_id = None
                if "/" in data_post:
                    msg_id = int(data_post.split("/")[-1])
                    oldest_msg_id = msg_id

                # ── Get message text ────────────────────────────────
                text_el = msg_div.find(class_="tgme_widget_message_text")
                text = text_el.get_text(" ", strip=True) if text_el else ""

                if not text or len(text) < 10:
                    continue

                # ── Get inline button links ─────────────────────────
                # These contain the actual Udemy/course links
                button_urls = []
                for btn in msg_div.find_all("a", class_="tgme_widget_message_inline_button"):
                    href = btn.get("href", "")
                    if href and href.startswith("http"):
                        button_urls.append(href)

                # ── Extract course from this message ────────────────
                course = self._extract_course(
                    msg_div, text, button_urls, channel, msg_id
                )
                if course:
                    courses.append(course)

            except Exception as e:
                print(f"[TG-Web] Message parse error: {e}")
                continue

        return courses, oldest_msg_id

    def _extract_course(
        self, msg_div, text: str, button_urls: list,
        channel: str, msg_id: int | None
    ) -> dict | None:
        """Extract a course dict from a Telegram message.

        Strategy (in order of priority):
        1. Direct Udemy coupon URL in message text → use it
        2. Udemy coupon URL in button link → use it
        3. Non-Udemy button link (bot/short/courson) → resolve it
        4. No usable URL → skip
        """
        udemy_url = None

        # ── Method 1: Direct Udemy coupon URL in text ───────────────
        coupon_match = UDEMY_COUPON_PATTERN.search(text)
        if coupon_match:
            udemy_url = coupon_match.group(0).rstrip("\"'/")
            print(f"  🔗 Direct Udemy coupon in text")

        # ── Method 2: Udemy coupon URL in button links ──────────────
        if not udemy_url:
            for btn_url in button_urls:
                if "udemy.com/course/" in btn_url and "couponCode=" in btn_url:
                    udemy_url = btn_url
                    print(f"  🔗 Udemy coupon in button")
                    break

        # ── Method 3: Resolve non-Udemy button links ────────────────
        if not udemy_url and button_urls:
            for btn_url in button_urls:
                # Skip hashtag links and t.me/channel post links
                if btn_url.startswith("https://t.me/"):
                    # But t.me/bot?start= links are worth resolving
                    if "?start=" not in btn_url:
                        continue

                # Skip same-domain hashtag links
                if "?q=%23" in btn_url:
                    continue

                print(f"  🔗 Resolving button: {btn_url[:80]}")
                time.sleep(RESOLVE_DELAY)
                resolved = self._resolve_url(btn_url)
                if resolved:
                    udemy_url = resolved
                    break

        # ── No Udemy URL found → skip ───────────────────────────────
        if not udemy_url:
            return None

        # ── Clean URL ────────────────────────────────────────────────
        udemy_url = self._clean_udemy_url(udemy_url)

        # ── Verify coupon code exists ────────────────────────────────
        if "couponCode=" not in udemy_url and "coupon_code=" not in udemy_url:
            print(f"  ⏭️ No couponCode — skipping (paid course)")
            return None

        # ── Extract title ────────────────────────────────────────────
        # Remove Udemy URLs from text first to get clean title
        title_text = re.sub(
            r'https?://(?:www\.)?udemy\.com/course/[^\s]*', '', text
        ).strip()

        # Remove channel promotions and share text
        title_text = re.sub(r'💌.*', '', title_text).strip()
        title_text = re.sub(r'@udemycodes.*', '', title_text, flags=re.IGNORECASE).strip()
        title_text = re.sub(r'@udemycoupons4u.*', '', title_text, flags=re.IGNORECASE).strip()
        title_text = re.sub(r'https?://t\.me/[^\s]*', '', title_text).strip()
        # Remove duration like [10.5hrs], [7.5hrs], [42.5hrs]
        title_text = re.sub(r'\[?\d+\.?\d*\s*hrs?\]?', '', title_text).strip()

        # Usually the first line of message text
        lines = [l.strip() for l in title_text.split('\n') if l.strip()]
        title = lines[0] if lines else "Free Course"

        # Clean common prefixes
        for prefix in TITLE_PREFIXES:
            if title.startswith(prefix):
                title = title.replace(prefix, '', 1).strip()

        # If title is still a URL or empty, try the Udemy course slug
        if title.startswith("http") or not title:
            slug_match = re.search(
                r'udemy\.com/course/([a-zA-Z0-9_-]+)', udemy_url
            )
            if slug_match:
                title = slug_match.group(1).replace('-', ' ').replace('_', ' ').title()
            else:
                title = "Free Course"

        # Remove hashtags, trailing brackets, artifacts
        title = re.sub(r'#\w+', '', title).strip()
        title = re.sub(r'[\[\]{(*]+$', '', title).strip()
        title = re.sub(r'\brs\b', '', title).strip()
        title = re.sub(r'\s*\[?\d+\.?\d*h\]?\s*', ' ', title).strip()
        title = re.sub(r'\s+', ' ', title).strip()
        # If title is too short/empty after cleanup, use URL slug
        if len(title) < 3:
            slug_match = re.search(
                r'udemy\.com/course/([a-zA-Z0-9_-]+)', udemy_url
            )
            if slug_match:
                title = slug_match.group(1).replace('-', ' ').replace('_', ' ').title()
        title = title[:200] or "Free Course"

        # ── Extract rating ───────────────────────────────────────────
        rating = self._extract_rating(text)

        # ── Smart Filter: rating too low → skip ──────────────────────
        if rating and float(rating) < MIN_RATING:
            print(f"  ⏭️ Skipped (rating {rating} < {MIN_RATING}): {title[:50]}")
            return None

        # ── Extract original price ───────────────────────────────────
        original_price = self._extract_price(text)

        # ── Extract image ────────────────────────────────────────────
        image_url = None
        img_tag = msg_div.find("img")
        if img_tag and img_tag.get("src"):
            src = img_tag["src"]
            # Only use CDN photo URLs, not channel avatars
            if "telesco.pe" in src or "cdn" in src:
                image_url = src

        # ── Build course ID ──────────────────────────────────────────
        entry_id = f"{channel}_{msg_id}" if msg_id else f"{channel}_{hash(title) % 100000}"

        print(f"  ✅ {title[:50]} → {udemy_url[:80]}")

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

    # ══════════════════════════════════════════════════════════════════
    #  URL RESOLUTION — follows intermediate links to get Udemy URL
    # ══════════════════════════════════════════════════════════════════

    def _resolve_url(self, url: str) -> str | None:
        """Follow a URL and extract the direct Udemy coupon URL from it.

        Handles:
        - t.me/bot?start= links → follow redirect to find Udemy URL
        - rb.gy short links → follow redirect
        - courson.xyz/coupon/ links → fetch page, search HTML
        - Any other URL → try to find Udemy coupon URL in response
        """
        try:
            resp = httpx.get(
                url, headers=HEADERS,
                timeout=15, follow_redirects=True
            )

            if resp.status_code != 200:
                print(f"    Resolve: HTTP {resp.status_code}")
                return None

            html = resp.text
            final_url = str(resp.url)

            # Check if we landed on a Udemy page directly
            if "udemy.com/course/" in final_url and "couponCode=" in final_url:
                print(f"    Resolve: direct redirect → Udemy")
                return final_url

            # Search HTML for Udemy coupon URL
            match = UDEMY_COUPON_PATTERN.search(html)
            if match:
                found = match.group(0).rstrip("\"'/")
                print(f"    Resolve: found in HTML")
                return found

            # BeautifulSoup fallback — search <a> tags
            soup = BeautifulSoup(html, "lxml")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "udemy.com/course/" in href and "couponCode=" in href:
                    print(f"    Resolve: found in <a> tag")
                    return href

            # JavaScript string literal fallback
            js_match = re.search(
                r'["\']('
                r'https?://(?:www\.)?udemy\.com'
                r'/course/[a-zA-Z0-9_-]+'
                r'/?\?[^"\']*couponCode=[^"\']+)'
                r'["\']',
                html
            )
            if js_match:
                print(f"    Resolve: found in JS")
                return js_match.group(1)

            # Check for another redirect URL in the page
            # (some pages use meta refresh or JS location)
            meta_match = re.search(
                r'content=["\']\d+;\s*url=(["\']?)([^"\'>\s]+)',
                html, re.IGNORECASE
            )
            if meta_match:
                redirect_url = meta_match.group(2)
                if "udemy.com" in redirect_url:
                    print(f"    Resolve: meta refresh → Udemy")
                    return redirect_url

            print(f"    Resolve: no Udemy coupon found")
            return None

        except Exception as e:
            print(f"    Resolve error: {e}")
            return None

    # ══════════════════════════════════════════════════════════════════
    #  HELPER METHODS
    # ══════════════════════════════════════════════════════════════════

    def _clean_udemy_url(self, url: str) -> str:
        """Clean a Udemy URL — remove tracking params, keep only coupon params."""
        try:
            parsed = up.urlparse(url)
            params = up.parse_qs(parsed.query)

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
        """Extract course rating from message text.

        t.me messages often use format: ⭐ 4.7 | $199.99
        """
        # Pattern: ⭐ 4.7 | or 4.7 | or rated 4.7
        match = RATING_PATTERN.search(text)
        if match:
            return match.group(1)

        # Fallback: standalone 4.X pattern near price
        simple = re.search(r'\b([4-5]\.\d)\b', text)
        if simple:
            return simple.group(1)

        return None
