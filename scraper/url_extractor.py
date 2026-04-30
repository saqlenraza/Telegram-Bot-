"""
CourseDrop Bot — URL Extractor
Regex-based extraction of Udemy coupon URLs from HTML content.
Used by the RSS fetcher as a secondary extraction method.
"""

import re
from bs4 import BeautifulSoup

UDEMY_URL_PATTERN = re.compile(
    r'https?://(?:www\.)?udemy\.com/course/[\w-]+/?(?:\?[^\s"\'<>]*)?'
)


def extract_udemy_url(text: str) -> str | None:
    """Extract the first Udemy coupon URL from text or HTML.

    Strategy:
    1. Try direct regex match on raw text (fastest path)
    2. Parse as HTML and look for <a> tags linking to udemy.com/course
    3. Return None if no Udemy URL is found
    """
    # Fast path — direct regex
    match = UDEMY_URL_PATTERN.search(text)
    if match:
        return match.group(0)

    # Slow path — parse HTML for <a> tags
    try:
        soup = BeautifulSoup(text, "lxml")
        for a in soup.find_all("a", href=True):
            if "udemy.com/course" in a["href"]:
                return a["href"]
    except Exception:
        pass

    return None


def extract_coupon_code(url: str) -> str | None:
    """Extract the couponCode parameter from a Udemy URL."""
    match = re.search(r'[?&]couponCode=([^&\s]+)', url)
    if match:
        return match.group(1)
    return None
