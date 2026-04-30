"""
CourseDrop Bot — Telegram Channel Poster
Sends formatted messages with course thumbnail to the Telegram channel.
Uses MarkdownV2 parse mode and send_photo for rich media posts.
Handles errors gracefully — bot never crashes on a single failed post.
"""

import re
from telegram import Bot
from telegram.constants import ParseMode
from config import BOT_TOKEN, CHANNEL_ID


class TelegramPoster:

    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)

    async def post(self, message: str, image_url: str = None) -> bool:
        """
        Send message to channel with optional thumbnail image.

        If image_url is provided, sends as photo with caption (rich media post).
        Otherwise falls back to plain text message.

        Returns True on success, False on failure.
        Never raises — bot keeps running even if one post fails.
        """
        try:
            if image_url:
                # Send as photo with caption — shows course thumbnail
                await self.bot.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=image_url,
                    caption=message,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            else:
                # Fallback: text-only message
                await self.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    disable_web_page_preview=False
                )
            return True
        except Exception as e:
            print(f"[Poster] MarkdownV2 failed: {e}")
            # If MarkdownV2 fails, strip all markdown and send clean plain text
            clean_text = self._strip_markdown(message)
            try:
                if image_url:
                    await self.bot.send_photo(
                        chat_id=CHANNEL_ID,
                        photo=image_url,
                        caption=clean_text,
                    )
                else:
                    await self.bot.send_message(
                        chat_id=CHANNEL_ID,
                        text=clean_text,
                        disable_web_page_preview=False
                    )
                return True
            except Exception as e2:
                # Final attempt — strip and send without image too
                try:
                    await self.bot.send_message(
                        chat_id=CHANNEL_ID,
                        text=clean_text[:1024] if len(clean_text) > 1024 else clean_text,
                    )
                    return True
                except Exception as e3:
                    print(f"[Poster] All attempts failed: {e3}")
                    return False

    def _strip_markdown(self, text: str) -> str:
        """Remove all MarkdownV2 formatting for clean plain text fallback.

        Removes backslash escapes, bold/italic markers, strikethrough,
        and link syntax — keeps the visible text readable.
        """
        # Remove backslash escapes (e.g. \. → ., \# → #, \| → |)
        text = re.sub(r'\\(.)', r'\1', text)
        # Remove strikethrough markers ~~
        text = text.replace('~~', '')
        # Remove bold/italic markers
        text = re.sub(r'[*_]', '', text)
        return text
