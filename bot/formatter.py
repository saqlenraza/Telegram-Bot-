"""
CourseDrop Bot — Message Formatter
Formats each course dict into a professional Telegram MarkdownV2 message.
Includes rating badge, price strikethrough, and category hashtags.
"""

import re


def format_message(course: dict) -> str:
    """Format a course dict into a professional Telegram MarkdownV2 message.

    Output format:
        ⭐ 4.6 | ~~$199.99~~ 🆓 100% OFF

        📚 *Course Title*

        🏷️ Category
        👥 X Students Enrolled

        👉 [Get Premium Course](url)

        #FreeCourses #Udemy #Category #Learning
    """
    title    = course.get("title") or "Free Course"
    url      = course.get("udemy_url") or course.get("source_url", "")
    category = course.get("category") or "Course"
    rating   = course.get("rating")
    price    = course.get("original_price")
    students = course.get("students")

    lines = []

    # ── Rating + Price line ─────────────────────────────────────────
    if rating:
        if price:
            # "⭐ 4.6 | ~~$199.99~~ 🆓 100% OFF"
            rating_escaped   = _escape_markdown_v2(rating)
            price_escaped    = _escape_markdown_v2(price)
            lines.append(f"⭐ {rating_escaped} \\| ~~{price_escaped}~~ 🆓 100% OFF — Enroll Free")
        else:
            rating_escaped = _escape_markdown_v2(rating)
            lines.append(f"⭐ {rating_escaped} \\| 🆓 100% OFF — Enroll Free")
    else:
        if price:
            price_escaped = _escape_markdown_v2(price)
            lines.append(f"~~{price_escaped}~~ 🆓 100% OFF — Enroll Free")
        else:
            lines.append("🆓 100% OFF — Enroll Free")

    # ── Blank line ──────────────────────────────────────────────────
    lines.append("")

    # ── Course Title (bold) ─────────────────────────────────────────
    title_escaped = _escape_markdown_v2(title)
    lines.append(f"📚 *{title_escaped}*")

    # ── Blank line ──────────────────────────────────────────────────
    lines.append("")

    # ── Category ────────────────────────────────────────────────────
    category_escaped = _escape_markdown_v2(category)
    lines.append(f"🏷️ {category_escaped}")

    # ── Students Enrolled ───────────────────────────────────────────
    if students:
        students_escaped = _escape_markdown_v2(str(students))
        lines.append(f"👥 {students_escaped} Students Enrolled")

    # ── Blank line ──────────────────────────────────────────────────
    lines.append("")

    # ── Get Premium Course button ───────────────────────────────────
    # In MarkdownV2, the URL part inside () needs minimal escaping:
    # only ) and \ need escaping — other chars are fine in the URL
    safe_url = url.replace('\\', '\\\\').replace(')', '\\)')
    lines.append(f"👉 [Get Premium Course]({safe_url})")

    # ── Blank line ──────────────────────────────────────────────────
    lines.append("")

    # ── Hashtags ────────────────────────────────────────────────────
    # In MarkdownV2, # must be escaped as \# so it renders as plain text
    category_hashtag = _make_category_hashtag(category)
    lines.append(f"\\#FreeCourses \\#Udemy {category_hashtag} \\#Learning")

    return "\n".join(lines)


def _escape_markdown_v2(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2.

    MarkdownV2 requires escaping these characters with backslash:
    _ * [ ] ( ) ~ ` > # + - = | { } . !
    """
    special_chars = r'_*[]()~`>#+-=|{}.!'
    escaped = []
    for char in text:
        if char in special_chars:
            escaped.append('\\' + char)
        else:
            escaped.append(char)
    return ''.join(escaped)


def _make_category_hashtag(category: str) -> str:
    """Convert category to PascalCase hashtag.

    Examples:
        "web development" → "#WebDevelopment"
        "IT & Software"   → "#ItSoftware"
        "data science"    → "#DataScience"
        "Python"          → "#Python"
    """
    # Remove special characters except spaces
    cleaned = re.sub(r'[^a-zA-Z0-9\s]', '', category)
    # Split into words and capitalize each
    words = cleaned.split()
    hashtag = ''.join(word.capitalize() for word in words)
    if not hashtag:
        hashtag = "Course"
    return f"\\#{hashtag}"
