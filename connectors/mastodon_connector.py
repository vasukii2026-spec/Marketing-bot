"""
Mastodon connector — posts via Mastodon's REST API using an access token.

Setup (free, ~2 minutes):
1. Log into your Mastodon account on the web (not the mobile app).
2. Go to Preferences -> Development -> New application.
3. Name it anything (e.g. "Vasukii Bot"), make sure the "write" scope is
   checked, click Submit.
4. Click into the app you just created and copy the "Access Token".
5. Set these two values in your .env file:
   MASTODON_INSTANCE=mastodon.social   (your instance's domain, no https://)
   MASTODON_ACCESS_TOKEN=paste_the_token_here

No app review, no cost, no waiting — Mastodon's API is open to any account
on any instance.
"""
import os
import mimetypes
import requests

MASTODON_INSTANCE = os.environ.get("MASTODON_INSTANCE", "").strip().rstrip("/")
MASTODON_ACCESS_TOKEN = os.environ.get("MASTODON_ACCESS_TOKEN", "")

MAX_CHARS = 500  # Mastodon's default limit (some instances allow more, but 500 is safe)


def _base_url():
    instance = MASTODON_INSTANCE
    if instance.startswith("http://") or instance.startswith("https://"):
        return instance.rstrip("/")
    return f"https://{instance}"


def _upload_media(media_url):
    media_resp = requests.get(media_url, timeout=30)
    media_resp.raise_for_status()
    filename = media_url.rsplit("/", 1)[-1]
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    resp = requests.post(
        f"{_base_url()}/api/v2/media",
        headers={"Authorization": f"Bearer {MASTODON_ACCESS_TOKEN}"},
        files={"file": (filename, media_resp.content, mime_type)},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def post_to_mastodon(content, media_path=None, media_type=None):
    """
    Publishes a status (toot) to Mastodon, optionally with one attached
    image or video.
    Returns (success: bool, error_message: str | None, platform_ref: str | None)
    platform_ref is the status id, used later to look up like/boost counts.
    """
    if not MASTODON_INSTANCE or not MASTODON_ACCESS_TOKEN:
        return False, "MASTODON_INSTANCE / MASTODON_ACCESS_TOKEN not set in .env.", None

    if len(content) > MAX_CHARS:
        return False, f"Post is {len(content)} chars, over Mastodon's {MAX_CHARS} limit.", None

    try:
        media_ids = []
        if media_path and media_path.startswith("http"):
            media_ids.append(_upload_media(media_path))

        resp = requests.post(
            f"{_base_url()}/api/v1/statuses",
            headers={"Authorization": f"Bearer {MASTODON_ACCESS_TOKEN}"},
            data={
                "status": content,
                **({"media_ids[]": media_ids} if media_ids else {}),
            },
            timeout=30,
        )
        resp.raise_for_status()
        status_id = resp.json().get("id")
        return True, None, status_id
    except requests.RequestException as e:
        return False, str(e), None
