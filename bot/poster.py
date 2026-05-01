"""
CourseDrop Bot — Telegram Channel Poster
Sends formatted messages with course thumbnail to the Telegram channel.
Uses MarkdownV2 parse mode and send_photo for rich media posts.
Multi-tier fallback: photo+MarkdownV2 → text+MarkdownV2 → stripped plain text.
Handles errors gracefully — bot never crashes on a single failed post.
"""

import os
import re
from telegram import Bot, InputFile
from telegram.constants import ParseMode
from config import BOT_TOKEN, CHANNEL_ID


class TelegramPoster:

    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)

    async def post(self, message: str, image_url: str = None) -> bool:
        """
        Send message to channel with optional thumbnail image.

        Tries MarkdownV2 first with photo, then text-only MarkdownV2,
        then stripped plain text. Never crashes — always returns True/False.

        Returns True on success, False on failure.
        """
        # ── Attempt 1: Photo with MarkdownV2 caption ──────────────────
        if image_url and os.path.exists(str(image_url)):
            try:
                with open(str(image_url), 'rb') as photo_file:
                    await self.bot.send_photo(
                        chat_id=CHANNEL_ID,
                        photo=photo_file,
                        caption=message,
                        parse_mode=ParseMode.MARKDOWN_V2,
                    )
                print("  ✅ Posted with photo + MarkdownV2")
                return True
            except Exception as e:
                print(f"  ⚠️ Photo+MarkdownV2 failed: {e}")
                # Fall through to text-only attempts

        # ── Attempt 2: Text message with MarkdownV2 ───────────────────
        try:
            await self.bot.send_message(
                chat_id=CHANNEL_ID,
                text=message,
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=False,
            )
            print("  ✅ Posted with MarkdownV2 (text only)")
            return True
        except Exception as e:
            print(f"  ⚠️ MarkdownV2 failed: {e}")

        # ── Attempt 3: Strip markdown, send clean plain text ──────────
        try:
            clean = self._strip_markdown(message)
            await self.bot.send_message(
                chat_id=CHANNEL_ID,
                text=clean,
                disable_web_page_preview=False,
            )
            print("  ✅ Posted with plain text (fallback)")
            return True
        except Exception as e:
            print(f"  ❌ All posting attempts failed: {e}")
            return False

    def _strip_markdown(self, text: str) -> str:
        """Remove all MarkdownV2 formatting for clean plain text fallback.

        Removes backslash escapes, bold/italic/strikethrough markers,
        and converts links [text](url) to readable 'text: url' format.
        """
        # Remove backslash escapes (e.g. \. → ., \# → #, \| → |)
        text = re.sub(r'\\(.)', r'\1', text)
        # Remove strikethrough markers ~~
        text = text.replace('~~', '')
        # Remove bold/italic markers
        text = re.sub(r'[*_]', '', text)
        # Fix links [text](url) → text: url
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1: \2', text)
        return text
