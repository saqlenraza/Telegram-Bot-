"""
CourseDrop Bot — Session String Generator
Run this ONCE locally to generate a SESSION_STRING for Telethon.
This string allows the bot to authenticate without interactive login on Render.

How to use:
1. Go to https://my.telegram.org
2. Create an application to get API_ID and API_HASH
3. Run this script: python generate_session.py
4. Enter your phone number and login code when prompted
5. Copy the SESSION_STRING output and set it in Render environment variables

IMPORTANT: Never share your SESSION_STRING — it grants full access to your Telegram account.
"""

from telethon.sync import TelegramClient
from telethon.sessions import StringSession


def main():
    print("=" * 60)
    print("CourseDrop Bot — Session String Generator")
    print("=" * 60)
    print()
    print("This will log into your Telegram account and generate")
    print("a session string for the bot to use on Render.")
    print()

    api_id   = input("Enter API_ID: ").strip()
    api_hash = input("Enter API_HASH: ").strip()

    if not api_id or not api_hash:
        print("❌ API_ID and API_HASH are required!")
        return

    with TelegramClient(StringSession(), int(api_id), api_hash) as client:
        session_string = client.session.save()
        print()
        print("=" * 60)
        print("✅ SESSION_STRING generated successfully!")
        print("=" * 60)
        print()
        print("Add this to your Render environment variables:")
        print()
        print(f"SESSION_STRING={session_string}")
        print()
        print("⚠️  IMPORTANT: Keep this secret — never commit it to GitHub!")


if __name__ == "__main__":
    main()
