"""
CourseDrop Bot — Telegram Channel Monitor
Uses Telethon to monitor source Telegram channels that post
free Udemy courses. Replaces RSS scraping which was blocked
by cloud server IPs on coupon aggregator websites.

IMPORTANT: TelegramClient is created inside the async function
(fetch_recent_courses), NOT in __init__. This fixes the Python 3.14
RuntimeError: "There is no current event loop in thread 'MainThread'".
"""

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
                  '🔥', '🆓', '✅', '⭐', '👉', '💯']

# Free course signals in message text
FREE_SIGNALS = [
    "100% off", "100% free", "free course",
    "coupon", "enroll free", "limited free",
    "free for", "freediscount", "100off"
]

# Paid course signals — if found without free signal, skip
PAID_SIGNALS = ["₹", "$9", "$19", "$29",
                "buy now", "purchase"]


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
                        course = self._parse_message(msg, channel)
                        if course:
                            channel_courses.append(course)
                    courses.extend(channel_courses)
                    print(f"[{channel}] Fetched {len(channel_courses)} courses")
                except Exception as e:
                    print(f"[{channel}] Error: {e}")

        return courses

    def _parse_message(self, msg, source_channel: str) -> dict | None:
        """Parse a Telegram message into a course dict.

        Only processes messages that:
        1. Contain a valid Udemy course URL
        2. Are confirmed to be FREE courses (have coupon code or free signals)
        Extracts title, price, rating from the message text where available.
        """
        if not msg.text:
            return None

        text = msg.text

        # Must contain a Udemy course URL — skip messages without one
        udemy_match = UDEMY_URL_PATTERN.search(text)
        if not udemy_match:
            return None

        udemy_url = udemy_match.group(0)

        # ── PROBLEM 1 FIX: Must be a free course ──────────────────────
        if not self._is_free_course(text, udemy_url):
            return None  # Skip paid courses

        # ── PROBLEM 2 FIX: Clean the URL — keep only coupon params ────
        udemy_url = self._clean_udemy_url(udemy_url)

        # ── Extract title ─────────────────────────────────────────────
        # First non-empty line is usually the title
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        title = lines[0] if lines else "Free Course"

        # Clean common prefixes used by coupon channels
        for prefix in TITLE_PREFIXES:
            if title.startswith(prefix):
                title = title.replace(prefix, '', 1).strip()

        # Truncate long titles
        title = title[:200] or "Free Course"

        # ── Extract image ─────────────────────────────────────────────
        # If the message has a photo, store its file_id for later use
        image_url = None
        if msg.photo:
            image_url = str(msg.photo.id)

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
            "image_url":      None,   # handled separately via tg_msg
            "original_price": original_price,
            "rating":         rating,
            "tg_msg":         msg,    # keep original message for photo access
        }

    def _is_free_course(self, text: str, url: str) -> bool:
        """Check if a course message is for a FREE course.

        Logic:
        1. If URL contains couponCode — definitely free (strongest signal)
        2. If text has FREE_SIGNALS — likely free
        3. If text has PAID_SIGNALS without FREE_SIGNALS — paid, skip
        4. Default: allow (messages from known free channels)
        """
        text_lower = text.lower()
        url_lower  = url.lower()

        # Strongest signal — coupon code in URL
        if "couponcode=" in url_lower:
            return True
        if "coupon_code=" in url_lower:
            return True

        # Free signals in text
        has_free = any(s in text_lower for s in FREE_SIGNALS)

        # Paid signals — if found without free signal, skip
        has_paid = any(s in text_lower for s in PAID_SIGNALS)

        if has_free and not has_paid:
            return True
        if has_paid and not has_free:
            return False

        # Default: if from known free course channels, allow
        return True

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
