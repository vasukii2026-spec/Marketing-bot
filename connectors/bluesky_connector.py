"""
Bluesky connector — posts via the AT Protocol REST API (no SDK needed).

Setup (free, ~2 minutes):
1. Log into the Bluesky account you want to post from.
2. Go to Settings -> Privacy and Security -> App Passwords -> Add App Password.
3. Name it anything (e.g. "vasukii-bot") and copy the password shown —
   you won't be able to see it again after closing that dialog.
4. Set these two values in your .env file:
   BLUESKY_HANDLE=yourname.bsky.social
   BLUESKY_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx

No developer app, no review queue, no cost — Bluesky's API is open to any
account. The only limit is a per-account rate limit (well above what a
manually-approved dashboard like this one will ever hit).

Note on media: images are supported below via uploadBlob + an embed.
Native video upload on Bluesky is a separate multi-step processing
pipeline (job status polling, transcoding) rather than one API call, so
it isn't wired up here yet — attaching a video to a Bluesky draft will
post text-only and flag that in the error message.
"""
import os
import mimetypes
import requests
from datetime import datetime, timezone

BLUESKY_HANDLE = os.environ.get("BLUESKY_HANDLE", "")
BLUESKY_APP_PASSWORD = os.environ.get("BLUESKY_APP_PASSWORD", "")
BLUESKY_PDS_URL = "https://bsky.social"

MAX_CHARS = 300


def _create_session():
    resp = requests.post(
        f"{BLUESKY_PDS_URL}/xrpc/com.atproto.server.createSession",
        json={"identifier": BLUESKY_HANDLE, "password": BLUESKY_APP_PASSWORD},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _upload_image_blob(access_jwt, image_url):
    mime_type = mimetypes.guess_type(image_url)[0] or "image/jpeg"
    img_resp = requests.get(image_url, timeout=30)
    img_resp.raise_for_status()
    data = img_resp.content
    resp = requests.post(
        f"{BLUESKY_PDS_URL}/xrpc/com.atproto.repo.uploadBlob",
        headers={"Authorization": f"Bearer {access_jwt}", "Content-Type": mime_type},
        data=data,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["blob"]


def post_to_bluesky(content, media_path=None, media_type=None):
    """
    Publishes a text post to Bluesky, optionally with one embedded image.
    Returns (success, error_message, platform_ref) — platform_ref is the
    record's AT-URI (used later to look up like/repost counts), or None
    on failure.
    """
    if not BLUESKY_HANDLE or not BLUESKY_APP_PASSWORD:
        return False, "BLUESKY_HANDLE / BLUESKY_APP_PASSWORD not set in .env.", None

    if len(content) > MAX_CHARS:
        return False, f"Post is {len(content)} chars, over Bluesky's {MAX_CHARS} limit.", None

    if media_path and media_type == "video":
        return False, "Video posting to Bluesky isn't supported yet — attach an image instead, or post text-only.", None

    try:
        session = _create_session()
        record = {
            "$type": "app.bsky.feed.post",
            "text": content,
            "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        }

        if media_path and media_path.startswith("http") and media_type == "image":
            blob = _upload_image_blob(session["accessJwt"], media_path)
            record["embed"] = {
                "$type": "app.bsky.embed.images",
                "images": [{"image": blob, "alt": ""}],
            }

        resp = requests.post(
            f"{BLUESKY_PDS_URL}/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {session['accessJwt']}"},
            json={
                "repo": session["did"],
                "collection": "app.bsky.feed.post",
                "record": record,
            },
            timeout=30,
        )
        resp.raise_for_status()
        uri = resp.json().get("uri")
        return True, None, uri
    except requests.RequestException as e:
        return False, str(e), None
