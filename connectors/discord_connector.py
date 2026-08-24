"""
Discord connector — posts via a Discord Webhook.

Setup (free, ~2 minutes):
1. In your Discord server, go to Server Settings -> Integrations -> Webhooks
2. Create a webhook, pick the channel, copy the Webhook URL
3. Set it as the DISCORD_WEBHOOK_URL environment variable
"""
import os
import requests

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")


def post_to_discord(content, media_path=None, media_type=None):
    """
    Posts a message to Discord via webhook, optionally attaching an image
    or video file (webhooks accept file uploads natively via multipart).
    Returns (success, error_message, platform_ref) — platform_ref is the
    message id (used later to look up reaction counts), or None on failure.
    """
    if not DISCORD_WEBHOOK_URL:
        return False, "DISCORD_WEBHOOK_URL not set. Create a webhook in your Discord server settings.", None

    # ?wait=true makes Discord return the created message (with its id)
    # instead of an empty 204 — we need that id for stats lookups later.
    webhook_url = DISCORD_WEBHOOK_URL
    sep = "&" if "?" in webhook_url else "?"
    post_url = f"{webhook_url}{sep}wait=true"

    try:
        if media_path and media_path.startswith("http"):
            media_resp = requests.get(media_path, timeout=30)
            media_resp.raise_for_status()
            filename = media_path.rsplit("/", 1)[-1]
            files = {"file": (filename, media_resp.content)}
            response = requests.post(
                post_url,
                data={"content": content},
                files=files,
                timeout=30,
            )
        else:
            response = requests.post(
                post_url,
                json={"content": content},
                timeout=15,
            )

        if response.status_code in (200, 201):
            message_id = None
            try:
                message_id = response.json().get("id")
            except ValueError:
                pass
            return True, None, message_id
        if response.status_code == 204:
            return True, None, None
        return False, f"Discord API returned {response.status_code}: {response.text}", None
    except requests.RequestException as e:
        return False, str(e), None
