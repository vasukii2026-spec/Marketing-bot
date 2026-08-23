"""
File storage for uploaded media (images/video attached to drafts).

Vercel's serverless functions have a read-only filesystem (except /tmp,
which is wiped after every single request), so we can't save uploads to
disk like the original local version did. Instead this uploads bytes to
Vercel Blob storage and stores the resulting public URL in the database.

Requires the BLOB_READ_WRITE_TOKEN env var, which Vercel sets automatically
once you create a Blob store and connect it to your project.
"""
import os
import uuid
import requests

BLOB_TOKEN = os.environ.get("BLOB_READ_WRITE_TOKEN", "")
BLOB_API_BASE = "https://blob.vercel-storage.com"


def is_configured():
    return bool(BLOB_TOKEN)


def upload_bytes(data: bytes, filename: str, content_type: str):
    """Uploads bytes to Vercel Blob and returns the public URL."""
    if not BLOB_TOKEN:
        raise RuntimeError(
            "BLOB_READ_WRITE_TOKEN is not set. Create a Blob store in your "
            "Vercel project (Storage tab) and connect it — the token gets "
            "added automatically."
        )
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    key = f"vasukii-media/{uuid.uuid4().hex}.{ext}"

    resp = requests.put(
        f"{BLOB_API_BASE}/{key}",
        data=data,
        headers={
            "Authorization": f"Bearer {BLOB_TOKEN}",
            "x-api-version": "7",
            "content-type": content_type,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["url"]


def delete_url(url: str):
    """Best-effort delete of a previously uploaded blob. Never raises."""
    if not BLOB_TOKEN or not url:
        return
    try:
        requests.post(
            f"{BLOB_API_BASE}/delete",
            json={"urls": [url]},
            headers={
                "Authorization": f"Bearer {BLOB_TOKEN}",
                "x-api-version": "7",
                "content-type": "application/json",
            },
            timeout=15,
        )
    except requests.RequestException:
        pass


def fetch_bytes(url: str):
    """Downloads a blob URL's content back into memory (connectors need
    the actual bytes to attach to Discord/Telegram/Bluesky, not just a URL)."""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.content
