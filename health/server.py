"""
CourseDrop Bot — Health Server
Minimal Flask server. UptimeRobot pings /health every 5 minutes
to prevent Render from sleeping the bot.
"""

from flask import Flask
from config import HEALTH_PORT
import threading

app = Flask(__name__)


@app.route("/health")
def health():
    return {"status": "ok", "bot": "CourseDrop", "running": True}, 200


@app.route("/")
def home():
    return "<h1>CourseDrop Bot is Running 🎓</h1>", 200


def start_health_server():
    """Run Flask in a background thread so it does not block the bot"""
    thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=HEALTH_PORT),
        daemon=True
    )
    thread.start()
    print(f"Health server running on port {HEALTH_PORT}")
