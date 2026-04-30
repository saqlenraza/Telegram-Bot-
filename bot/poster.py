"""
CourseDrop Bot — Telegram Channel Poster
Sends formatted messages to the Telegram channel.
Handles errors gracefully — bot never crashes on a single failed post.
"""

from telegram import Bot
from telegram.constants import ParseMode
from config import BOT_TOKEN, CHANNEL_ID


class TelegramPoster:

    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)

    async def post(self, message: str) -> bool:
        """
        Send message to channel.
        Returns True on success, False on failure.
        Never raises — bot keeps running even if one post fails.
        """
        try:
            await self.bot.send_message(
                chat_id            = CHANNEL_ID,
                text               = message,
                parse_mode         = ParseMode.MARKDOWN,
                disable_web_page_preview = False  # Shows Udemy course thumbnail
            )
            return True
        except Exception as e:
            print(f"[Poster] Failed to send: {e}")
            return False
