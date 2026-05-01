"""
CourseDrop Bot — Entry Point
The brain. Starts health server, monitors Telegram source channels,
then schedules every 20 minutes forever.
"""

import asyncio
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import (SCRAPE_INTERVAL_MINUTES, POST_DELAY_SECONDS,
                    BOT_TOKEN, CHANNEL_ID,
                    API_ID, API_HASH, SOURCE_CHANNELS)
from scraper.telegram_monitor import TelegramMonitor
from filters.dedup import DedupFilter
from bot.formatter import format_message
from bot.poster import TelegramPoster
from db.database import Database
from health.server import start_health_server

# ── Initialise components ─────────────────────────────────────────────
SESSION_STRING = os.getenv("SESSION_STRING", "")

# Create monitor — __init__ no longer creates TelegramClient
# (that happens inside fetch_recent_courses in async context)
monitor = TelegramMonitor(
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING
)

db       = Database()
dedup    = DedupFilter(db)
poster   = TelegramPoster()


async def check_bot_access():
    """Verify bot can access the Telegram channel before starting."""
    if not BOT_TOKEN:
        print("❌ FATAL: BOT_TOKEN is not set. Set it in Render environment variables.")
        return False

    try:
        from telegram import Bot
        bot = Bot(token=BOT_TOKEN)
        me = await bot.get_me()
        print(f"🤖 Bot authenticated: @{me.username} ({me.first_name})")
    except Exception as e:
        print(f"❌ FATAL: Bot token invalid: {e}")
        return False

    # Try to check channel access
    try:
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text="🚀 CourseDrop Bot is now online! Free courses coming your way...",
        )
        print(f"✅ Successfully posted to channel {CHANNEL_ID}")
    except Exception as e:
        print(f"⚠️  WARNING: Cannot post to channel '{CHANNEL_ID}': {e}")
        print(f"   Make sure:")
        print(f"   1. The channel exists")
        print(f"   2. The bot is added as an Administrator")
        print(f"   3. CHANNEL_ID is set correctly (e.g. @CourseDrop or -1001234567890)")
        print(f"   Bot will keep running and retry on each cycle...")
        return True  # Don't crash — just warn

    return True


async def check_telethon_access():
    """Verify Telethon session is valid by trying to connect."""
    if not monitor.ready:
        print("⚠️  Telethon not configured — skipping source channel monitoring.")
        print("   To enable:")
        print("   1. Go to https://my.telegram.org → create app → get API_ID + API_HASH")
        print("   2. Run generate_session.py locally → get SESSION_STRING")
        print("   3. Set API_ID, API_HASH, SESSION_STRING in Render environment variables")
        return False

    try:
        # Create a temporary client to verify session works
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        client = TelegramClient(
            StringSession(SESSION_STRING),
            API_ID,
            API_HASH
        )
        async with client:
            me = await client.get_me()
            print(f"📱 Telethon authenticated: {me.first_name} (@{me.username})")
    except Exception as e:
        print(f"❌ Telethon session invalid: {e}")
        print("   Run generate_session.py locally to get a new SESSION_STRING.")
        monitor.ready = False
        return False

    return True


async def run_cycle():
    """One complete monitor-filter-post cycle"""
    print("\n🔄 Starting monitoring cycle...")

    # Check if Telethon is ready before fetching
    if not monitor.ready:
        print("⏸️  Telethon not configured — skipping this cycle.")
        print("   Set API_ID, API_HASH, SESSION_STRING in Render env vars.")
        return

    posted_count = 0
    skipped_count = 0
    failed_count = 0

    try:
        # Fetch recent messages from source Telegram channels
        courses = await monitor.fetch_recent_courses(
            SOURCE_CHANNELS, limit=20
        )
        print(f"📥 Total courses fetched: {len(courses)}")
    except Exception as e:
        print(f"❌ Failed to fetch courses: {e}")
        print("   Will retry on next cycle...")
        return

    for course in courses:
        try:
            # Skip duplicates
            if dedup.is_duplicate(course["id"]):
                skipped_count += 1
                continue

            # Format Telegram message
            message = format_message(course)

            # Post to channel (with thumbnail if available)
            success = await poster.post(
                message=message,
                image_url=course.get("image_url")
            )

            if success:
                dedup.mark_posted(course)
                posted_count += 1
                print(f"  ✅ Posted: {course.get('title', 'Untitled')[:60]}")
                await asyncio.sleep(POST_DELAY_SECONDS)
            else:
                failed_count += 1
                print(f"  ❌ Failed: {course.get('title', 'Untitled')[:60]}")

        except Exception as e:
            failed_count += 1
            print(f"  ❌ Error processing course: {e}")
            continue  # NEVER crash — skip and move to next

    # Cleanup old DB records
    db.cleanup_old()
    print(f"✨ Cycle complete. Posted: {posted_count} | Skipped (dupes): {skipped_count} | Failed: {failed_count}\n")


async def main():
    print("🚀 CourseDrop Bot starting...")
    print(f"   Channel: {CHANNEL_ID}")
    print(f"   Source channels: {len(SOURCE_CHANNELS)}")
    print(f"   Telethon ready: {'Yes ✅' if monitor.ready else 'No ⚠️ (needs env vars)'}")
    print(f"   Scrape interval: every {SCRAPE_INTERVAL_MINUTES} minutes")

    # Check bot token access — MUST have this
    bot_ok = await check_bot_access()
    if not bot_ok:
        print("❌ Cannot continue without valid BOT_TOKEN. Exiting.")
        return

    # Check Telethon session access (non-fatal if missing)
    await check_telethon_access()

    # Start UptimeRobot health endpoint
    start_health_server()

    # Run immediately on startup (will skip gracefully if Telethon not ready)
    await run_cycle()

    # Schedule every N minutes
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        lambda: asyncio.create_task(run_cycle()),
        trigger   = "interval",
        minutes   = SCRAPE_INTERVAL_MINUTES
    )
    scheduler.start()
    print(f"⏰ Scheduler running — cycle every {SCRAPE_INTERVAL_MINUTES} min")

    # Keep running forever
    while True:
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
