"""
CourseDrop Bot — Central Configuration
All settings live here. Never hardcode tokens in other files.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ──────────────────────────────────────────────────────────
BOT_TOKEN  = os.getenv("BOT_TOKEN")        # Set in Render env variables
CHANNEL_ID = os.getenv("CHANNEL_ID", "@CourseDrop")  # Your channel username

# ── RSS Feed Sources ──────────────────────────────────────────────────
RSS_FEEDS = [
    {"url": "https://www.tutorialbar.com/feed/",    "name": "TutorialBar"},
    {"url": "https://couponscorpion.com/feed/",     "name": "CouponScorpion"},
    {"url": "https://www.real.discount/rss/",       "name": "RealDiscount"},
    {"url": "https://www.discudemy.com/feed",       "name": "Discudemy"},
    {"url": "https://udemyfreebies.com/feed",       "name": "Udemyfreebies"},
]

# ── Scheduler ─────────────────────────────────────────────────────────
SCRAPE_INTERVAL_MINUTES = 20   # Run every 20 minutes
POST_DELAY_SECONDS      = 3    # Gap between Telegram posts (rate limit)

# ── Database ──────────────────────────────────────────────────────────
DB_PATH       = "coursedrop.db"
CLEANUP_DAYS  = 14             # Delete records older than 14 days

# ── Health Server ─────────────────────────────────────────────────────
HEALTH_PORT = int(os.getenv("PORT", 8080))  # Render sets PORT automatically
