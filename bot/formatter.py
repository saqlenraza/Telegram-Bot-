"""
CourseDrop Bot — Message Formatter
Formats each course dict into a beautiful Telegram Markdown message.
Includes relevant emoji by category for visual appeal.
"""

# Category → Emoji mapping
CATEGORY_EMOJI = {
    "development":        "💻",
    "programming":        "💻",
    "python":             "🐍",
    "web development":    "🌐",
    "design":             "🎨",
    "graphic design":     "🎨",
    "business":           "💼",
    "marketing":          "📣",
    "finance":            "💰",
    "music":              "🎵",
    "photography":        "📷",
    "health":             "❤️",
    "fitness":            "💪",
    "data science":       "📊",
    "machine learning":   "🤖",
    "artificial":         "🤖",
    "it & software":      "🖥️",
    "office productivity":"📋",
    "personal development":"🌱",
    "teaching":           "📚",
    "language":           "🗣️",
}


def get_emoji(category: str | None) -> str:
    """Get the most relevant emoji for a course category."""
    if not category:
        return "🎓"  # default
    cat = category.lower()
    for key, emoji in CATEGORY_EMOJI.items():
        if key in cat:
            return emoji
    return "🎓"  # default


def format_message(course: dict) -> str:
    """Format a course dict into a Telegram Markdown message.

    Output format:
        {emoji} *FREE Udemy Course!*

        📚 *{title}*

        🏷️ Category: {category}
        ⚡ Limited Time — Expires Soon!

        👉 [Enroll FREE Now]({url})

        🔔 Get more free courses → @CourseDrop

        #FreeCourse #Udemy #LearnFree #FreeEducation #{source}
    """
    category = course.get("category") or "Course"
    emoji    = get_emoji(category)
    title    = course.get("title") or "Free Course"
    url      = course.get("udemy_url") or course.get("source_url", "")
    source   = course.get("source") or "CourseDrop"

    # Escape Markdown special characters in title
    # Only escape characters that would break Markdown parsing
    title = _escape_markdown(title)

    return (
        f"{emoji} *FREE Udemy Course!*\n"
        f"\n"
        f"📚 *{title}*\n"
        f"\n"
        f"🏷️ Category: {category}\n"
        f"⚡ Limited Time — Expires Soon!\n"
        f"\n"
        f"👉 [Enroll FREE Now]({url})\n"
        f"\n"
        f"🔔 Get more free courses → @CourseDrop\n"
        f"\n"
        f"#FreeCourse #Udemy #LearnFree #FreeEducation #{source.replace(' ', '')}"
    )


def _escape_markdown(text: str) -> str:
    """Escape Markdown special characters in text that would break formatting.

    Only escapes characters that could interfere with Telegram Markdown:
    * (bold), _ (italic), [ (link start)
    Does NOT escape characters inside URLs — those are handled by Telegram.
    """
    # Replace problematic chars but preserve readability
    text = text.replace("*", "✦")
    text = text.replace("_", " ")
    text = text.replace("[", "(")
    text = text.replace("]", ")")
    return text
