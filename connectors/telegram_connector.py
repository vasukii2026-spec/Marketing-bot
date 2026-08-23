"""
Telegram connector — posts via the Telegram Bot API.

Setup (free, ~2 minutes):
1. In Telegram, message @BotFather and send /newbot. Follow the prompts.
   It gives you a token like 123456789:AAF... — that's TELEGRAM_BOT_TOKEN.
2. Create (or use) a channel, then add your bot as an admin of it with
   "Post Messages" permission.
3. Get the chat id:
   - Public channel: it's just "@yourchannelname" — no lookup needed.
   - Private channel: post any message in it, then visit
     https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates in a browser and
     read the numeric "chat":{"id": ...} value (looks like -1001234567890).
4. Set these two values in your .env file:
   TELEGRAM_BOT_TOKEN=123456789:AAF...
   TELEGRAM_CHAT_ID=@yourchannelname (or the numeric id)

Free, no review process, no rate-limit concerns at this posting volume.
"""
import os
import requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

API_BASE = "https://api.telegram.org/bot{token}/{method}"


def post_to_telegram(content, media_path=None, media_type=None):
    """
    Sends a message (optionally with a photo or video) to the configured
    Telegram chat/channel. When media is attached, `content` becomes the
    caption (Telegram captions are capped at 1024 chars).
    Returns (success: bool, error_message: str | None)
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False, "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set in .env."

    try:
        if media_path and media_path.startswith("http"):
            method = "sendVideo" if media_type == "video" else "sendPhoto"
            field = "video" if media_type == "video" else "photo"
            caption = content[:1024]
            media_resp = requests.get(media_path, timeout=60)
            media_resp.raise_for_status()
            filename = media_path.rsplit("/", 1)[-1]
            resp = requests.post(
                API_BASE.format(token=TELEGRAM_BOT_TOKEN, method=method),
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
                files={field: (filename, media_resp.content)},
                timeout=60,
            )
        else:
            resp = requests.post(
                API_BASE.format(token=TELEGRAM_BOT_TOKEN, method="sendMessage"),
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": content,
                    "disable_web_page_preview": False,
                },
                timeout=15,
            )

        data = resp.json()
        if resp.status_code == 200 and data.get("ok"):
            return True, None
        return False, data.get("description", f"Telegram API returned {resp.status_code}")
    except requests.RequestException as e:
        return False, str(e)
