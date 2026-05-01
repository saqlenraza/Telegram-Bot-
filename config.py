"""
CourseDrop Bot — Central Configuration
All settings live here. Never hardcode tokens in other files.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram Bot ──────────────────────────────────────────────────────
BOT_TOKEN  = os.getenv("BOT_TOKEN")        # Set in Render environment variables
CHANNEL_ID = os.getenv("CHANNEL_ID", "@udemycoursedrop")  # Your channel username

# ── Source Channels to Monitor ────────────────────────────────────────
# These Telegram channels post free Udemy courses — we scrape their
# public web previews at t.me/s/channel (no authentication needed)
SOURCE_CHANNELS = [
    "Udemy7",
    "Udemy_Courses_Free_Daily",
    "Udemy4U",
]

# ── Scheduler ─────────────────────────────────────────────────────────
SCRAPE_INTERVAL_MINUTES = 30   # Run every 30 minutes
POST_DELAY_SECONDS      = 3    # Gap between Telegram posts (rate limit)

# ── Database ──────────────────────────────────────────────────────────
DB_PATH       = "coursedrop.db"
CLEANUP_DAYS  = 14             # Delete records older than 14 days

# ── Health Server ─────────────────────────────────────────────────────
HEALTH_PORT = int(os.getenv("PORT", 8080))  # Render sets PORT automatically
