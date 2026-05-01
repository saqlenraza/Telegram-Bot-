"""
CourseDrop Bot — Telegram Channel Monitor
Uses Telethon to monitor source Telegram channels that post
free Udemy courses. Replaces RSS scraping which was blocked
by cloud server IPs on coupon aggregator websites.

IMPORTANT: TelegramClient is created inside the async function
(fetch_recent_courses), NOT in __init__. This fixes the Python 3.14
RuntimeError: "There is no current event loop in thread 'MainThread'".
"""

import asyncio
import os
import re
import urllib.parse as up
from telethon import TelegramClient
from telethon.sessions import StringSession

# Updated pattern — captures full URL with coupon code parameters
UDEMY_URL_PATTERN = re.compile(
    r'https?://(?:www\.)?udemy\.com/course/'
    r'[a-zA-Z0-9_-]+/?'
    r'(?:\?[^"\'\s<>\)]*)?'
)

PRICE_PATTERN = re.compile(r'[\$£€][\d,]+\.?\d*')

RATING_PATTERN = re.compile(
    r'(?:rating[:\s]*|rated[:\s]*|stars?[:\s]*)?([4-5]\.\d)',
    re.IGNORECASE
)

# Prefixes commonly used by coupon channels — strip these to get clean title
TITLE_PREFIXES = ['FREE:', 'Free:', '🎓', '📚', '100% OFF', '[100% OFF]',
                  '🔥', '🆓', '✅', '⭐', '👉', '💯', '📢', '🎁',
                  'Free Course:', 'FREE COURSE:', 'Udemy Free:',
                  'Free Udemy Course:', '[Free]', '[FREE]']

# Free course signals in message text — expanded to catch more variations
FREE_SIGNALS = [
    "100% off", "100% free", "free course",
    "coupon", "enroll free", "limited free",
    "free for", "freediscount", "100off",
    "free udemy", "0 free", "no cost",
    "zero cost", "off 100%", "100 off",
    "$0", "₹0", "0.00",
    "free coupon", "free enrollment",
    "grab free", "get free", "free access",
    "coupon code", "couponcode",
    "deal code", "deal_code",
    "100% discount", "full discount",
]

# Paid course signals — if found without free signal, skip
# Expanded to catch more paid patterns
PAID_SIGNALS = [
    "₹", "$9", "$19", "$29",
    "buy now", "purchase",
    "$4.99", "$9.99", "$12.99", "$14.99",
    "$24.99", "$34.99", "$49.99", "$74.99", "$99.99",
    "₹449", "₹649", "₹999", "₹1999",
    "discounted price", "sale price",
    "subscribe", "premium access", "pro plan",
    "paid course", "not free",
]

# Temp directory for downloaded photos
PHOTO_DIR = "/tmp/coursedrop_photos"


class TelegramMonitor:

    def __init__(self, api_id, api_hash, session_string):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_string = session_string
        self.ready = bool(api_id and api_hash and session_string)

    async def fetch_recent_courses(
        self,
        source_channels: list,
        limit: int = 20
    ) -> list:
        """
        Fetch recent messages from source channels.
        Returns list of course dicts — same format as RSSFetcher
        so the rest of the pipeline (dedup, formatter, poster) works unchanged.

        TelegramClient is created INSIDE this async function to avoid
        the Python 3.14 event loop error on module-level instantiation.
        """
        if not self.ready:
            print("Telethon not configured — skipping")
            return []

        courses = []

        # Ensure photo directory exists
        os.makedirs(PHOTO_DIR, exist_ok=True)

        # Create client INSIDE async function — fixes Python 3.14 issue
        client = TelegramClient(
            StringSession(self.session_string),
            self.api_id,
            self.api_hash
        )

        async with client:
            for channel in source_channels:
                try:
                    msgs = await client.get_messages(
                        channel, limit=limit
                    )
                    channel_courses = []
                    for msg in msgs:
                        course = await asyncio.to_thread(
                            self._parse_message, msg, channel
                        )
                        if course:
                            # ── Download photo if message has one ──────
                            if msg.photo:
                                try:
                                    photo_path = await client.download_media(
                                        msg,
                                        file=os.path.join(PHOTO_DIR, f"{msg.id}.jpg")
                                    )
                                    if photo_path:
                                        course["image_url"] = photo_path
                                        print(f"  📸 Downloaded photo: {photo_path}")
                                except Exception as e:
                                    print(f"  ⚠️ Photo download failed: {e}")

                            channel_courses.append(course)
                    courses.extend(channel_courses)
                    print(f"[{channel}] Fetched {len(channel_courses)} FREE courses")
                except Exception as e:
                    print(f"[{channel}] Error: {e}")

        return courses

    # Broader URL pattern — catches intermediate links too
    ANY_URL_PATTERN = re.compile(
        r'https?://[^"\'\s<>)]+'
    )

    def _parse_message(self, msg, source_channel: str) -> dict | None:
        """Parse a Telegram message into a course dict.

        Only processes messages that:
        1. Contain a URL (Udemy direct or intermediate link)
        2. Resolve to a Udemy coupon URL via _resolve_to_udemy_url()
        3. Are confirmed to be FREE courses (have coupon code)
        Extracts title, price, rating from the message text where available.
        """
        if not msg.text:
            return None

        text = msg.text

        # ── Find the first URL in the message ────────────────────────
        # Try Udemy URL first (direct link)
        udemy_match = UDEMY_URL_PATTERN.search(text)
        if udemy_match:
            raw_url = udemy_match.group(0)
        else:
            # No direct Udemy URL — look for any URL (intermediate link)
            any_match = self.ANY_URL_PATTERN.search(text)
            if not any_match:
                return None
            raw_url = any_match.group(0)

        # ── Resolve intermediate URL to direct Udemy coupon link ─────
        resolved = self._resolve_to_udemy_url(raw_url)
        if not resolved:
            return None  # No free coupon found — skip

        udemy_url = resolved

        # ── Clean the URL — keep only coupon params ────────────────
        udemy_url = self._clean_udemy_url(udemy_url)

        # ── Verify coupon code exists after cleaning ────────────────
        if "couponCode=" not in udemy_url and "coupon_code=" not in udemy_url and "deal_code=" not in udemy_url:
            return None  # No coupon after cleaning — likely paid

        # ── Extract title ─────────────────────────────────────────────
        # First non-empty line is usually the title
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        title = lines[0] if lines else "Free Course"

        # Clean common prefixes used by coupon channels
        for prefix in TITLE_PREFIXES:
            if title.startswith(prefix):
                title = title.replace(prefix, '', 1).strip()

        # If title is just a URL, try the next line
        if title.startswith("http") and len(lines) > 1:
            title = lines[1]
            for prefix in TITLE_PREFIXES:
                if title.startswith(prefix):
                    title = title.replace(prefix, '', 1).strip()

        # Truncate long titles
        title = title[:200] or "Free Course"

        # ── Extract price from text ───────────────────────────────────
        original_price = self._extract_price(text)

        # ── Extract rating from text ──────────────────────────────────
        rating = self._extract_rating(text)

        # ── Unique ID = channel + message ID ──────────────────────────
        entry_id = f"{source_channel}_{msg.id}"

        return {
            "id":             entry_id,
            "title":          title,
            "udemy_url":      udemy_url,
            "source_url":     udemy_url,
            "source":         source_channel,
            "category":       "Course",
            "image_url":      None,   # filled later by fetch_recent_courses
            "original_price": original_price,
            "rating":         rating,
        }

    def _resolve_to_udemy_url(self, url: str) -> str | None:
        """Resolve a URL (direct or intermediate) to a Udemy coupon URL.

        Handles:
        - Direct Udemy URLs with couponCode → return as-is
        - Direct Udemy URLs WITHOUT couponCode → None (paid course)
        - Intermediate links (e.g. discudemy.com) → fetch page,
          search for Udemy coupon URL in HTML response

        Returns the resolved Udemy coupon URL, or None if no coupon found.
        """
        import httpx

        HEADERS = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0;"
                         " Win64; x64) AppleWebKit/537.36"
        }

        UDEMY_COUPON_PATTERN = re.compile(
            r'https?://(?:www\.)?udemy\.com/course/'
            r'[a-zA-Z0-9_-]+/?'
            r'\?[^"\'\s<>]*couponCode=[^"\'\s<>]+'
        )

        try:
            # Already direct Udemy coupon link
            if "udemy.com/course/" in url:
                if "couponCode=" in url:
                    return url
                else:
                    return None  # Paid — skip

            # Fetch intermediate page
            resp = httpx.get(
                url, headers=HEADERS,
                timeout=15, follow_redirects=True
            )
            if resp.status_code != 200:
                return None

            # Search for Udemy coupon URL in response text
            match = UDEMY_COUPON_PATTERN.search(resp.text)
            if match:
                udemy_url = match.group(0)
                # Clean any trailing HTML artifacts
                udemy_url = udemy_url.split('"')[0]
                udemy_url = udemy_url.split("'")[0]
                return udemy_url

            # BeautifulSoup fallback — search all <a> tags
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "lxml")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if ("udemy.com/course/" in href
                        and "couponCode=" in href):
                    return href

            return None  # No coupon found — skip

        except Exception as e:
            print(f"[Resolver] Error resolving {url[:60]}: {e}")
            return None

    def _is_free_course(self, text: str, url: str) -> bool:
        """Check if a course message is for a FREE course.

        STRICT MODE — defaults to False (skip uncertain courses).

        Logic:
        1. If URL contains couponCode — definitely free (strongest signal)
        2. If text has FREE_SIGNALS — likely free
        3. If text has PAID_SIGNALS without FREE_SIGNALS — paid, skip
        4. Default: SKIP (strict — don't post uncertain courses)
        """
        text_lower = text.lower()
        url_lower  = url.lower()

        # Strongest signal — coupon code in URL
        if "couponcode=" in url_lower:
            return True
        if "coupon_code=" in url_lower:
            return True
        if "deal_code=" in url_lower:
            return True

        # Free signals in text
        has_free = any(s in text_lower for s in FREE_SIGNALS)

        # Paid signals — if found without free signal, skip
        has_paid = any(s in text_lower for s in PAID_SIGNALS)

        if has_free and not has_paid:
            return True
        if has_paid and not has_free:
            return False
        if has_free and has_paid:
            # Both signals present — free signal takes priority
            # (source channels often show original price alongside FREE label)
            return True

        # STRICT DEFAULT: skip uncertain courses
        # Messages without coupon code AND without free signals
        # are likely expired deals or paid courses
        print(f"  ⏭️ Skipped (no free signal): {text[:80]}...")
        return False

    def _clean_udemy_url(self, url: str) -> str:
        """Clean a Udemy URL — remove tracking params, keep only couponCode.

        Example:
            Input:  https://www.udemy.com/course/python/?xref=abc&couponCode=FREE123&ref=mail
            Output: https://www.udemy.com/course/python/?couponCode=FREE123
        """
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
                # No coupon params — strip all tracking params
                clean_url = up.urlunparse((
                    parsed.scheme, parsed.netloc,
                    parsed.path, '', '', ''
                ))
            return clean_url
        except Exception:
            return url

    def _extract_price(self, text: str) -> str | None:
        """Extract original price from message text.

        Looks for patterns like $199.99, £49.99, €29.99.
        """
        match = PRICE_PATTERN.search(text)
        if match:
            return match.group(0)
        return None

    def _extract_rating(self, text: str) -> str | None:
        """Extract course rating from message text.

        Looks for patterns like "4.6" near "rating" keyword,
        or standalone "4.X" ratings in the text.
        """
        # Look for explicit "rating" mentions
        match = RATING_PATTERN.search(text)
        if match:
            return match.group(1)

        # Fallback: look for standalone 4.X pattern
        simple_rating = re.search(r'\b([4-5]\.\d)\b', text)
        if simple_rating:
            return simple_rating.group(1)

        return None
