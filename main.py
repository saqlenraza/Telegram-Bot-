"""
CourseDrop Bot — Entry Point
The brain. Starts health server, runs first scrape immediately,
then schedules every 20 minutes forever.
"""

import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import RSS_FEEDS, SCRAPE_INTERVAL_MINUTES, POST_DELAY_SECONDS, BOT_TOKEN, CHANNEL_ID
from scraper.rss_fetcher import RSSFetcher
from filters.dedup import DedupFilter
from bot.formatter import format_message
from bot.poster import TelegramPoster
from db.database import Database
from health.server import start_health_server

# ── Initialise all components ──────────────────────────────────────────
fetcher  = RSSFetcher()
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


async def run_cycle():
    """One complete scrape-filter-post cycle"""
    print("\n🔄 Starting scrape cycle...")
    posted_count = 0
    skipped_count = 0
    failed_count = 0

    courses = fetcher.fetch_all(RSS_FEEDS)
    print(f"📥 Total entries fetched: {len(courses)}")

    for course in courses:
        try:
            # Skip duplicates
            if dedup.is_duplicate(course["id"]):
                skipped_count += 1
                continue

            # Format Telegram message
            message = format_message(course)

            # Post to channel
            success = await poster.post(message)

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
    print(f"   Scrape interval: every {SCRAPE_INTERVAL_MINUTES} minutes")

    # Check bot access before starting
    await check_bot_access()

    # Start UptimeRobot health endpoint
    start_health_server()

    # Run immediately on startup
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
