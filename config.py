"""
CourseDrop Bot — Central Configuration
All settings live here. Never hardcode tokens in other files.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram Bot ──────────────────────────────────────────────────────
BOT_TOKEN  = os.getenv("BOT_TOKEN")        # Set in Render environment variables
CHANNEL_ID = os.getenv("CHANNEL_ID", "@CourseDrop")  # Your channel username

# ── Scheduler ─────────────────────────────────────────────────────────
SCRAPE_INTERVAL_MINUTES = 30   # Run every 30 minutes
POST_DELAY_SECONDS      = 3    # Gap between Telegram posts (rate limit)

# ── Database ──────────────────────────────────────────────────────────
DB_PATH       = "coursedrop.db"
CLEANUP_DAYS  = 14             # Delete records older than 14 days

# ── Health Server ─────────────────────────────────────────────────────
HEALTH_PORT = int(os.getenv("PORT", 8080))  # Render sets PORT automatically
