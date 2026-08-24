"""
Post performance tracking — pulls like/repost/reply counts back for posts
that already went out, using each platform's PUBLIC read endpoints (no
extra API keys or bot permissions needed beyond what posting already uses).

Coverage:
- Bluesky: full support (public getPostThread endpoint, no auth needed).
- Mastodon: full support (public status lookup, no auth needed).
- Discord: reaction counts only, via the same webhook used to post
  (Discord webhooks can read back their own messages).
- Telegram: NOT supported — the Bot API doesn't expose view/reaction
  counts for channel posts to bots that aren't full channel admins with
  extra permissions. Calls for telegram return None (skipped, not an error).
"""
import os
import requests

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
BLUESKY_PUBLIC_API = "https://public.api.bsky.app"
MASTODON_INSTANCE = os.environ.get("MASTODON_INSTANCE", "").strip().rstrip("/")


def _mastodon_base_url():
    instance = MASTODON_INSTANCE
    if instance.startswith("http://") or instance.startswith("https://"):
        return instance.rstrip("/")
    return f"https://{instance}"


def fetch_stats(platform, platform_ref):
    """
    Returns {"likes": int, "reposts": int, "replies": int} or None if this
    platform/ref combination can't be looked up (unsupported platform,
    missing ref, or the request failed).
    """
    if not platform_ref:
        return None

    try:
        if platform == "bluesky":
            resp = requests.get(
                f"{BLUESKY_PUBLIC_API}/xrpc/app.bsky.feed.getPostThread",
                params={"uri": platform_ref, "depth": 0},
                timeout=15,
            )
            resp.raise_for_status()
            post = resp.json()["thread"]["post"]
            return {
                "likes": post.get("likeCount", 0),
                "reposts": post.get("repostCount", 0),
                "replies": post.get("replyCount", 0),
            }

        if platform == "mastodon":
            if not MASTODON_INSTANCE:
                return None
            resp = requests.get(
                f"{_mastodon_base_url()}/api/v1/statuses/{platform_ref}",
                timeout=15,
            )
            resp.raise_for_status()
            status = resp.json()
            return {
                "likes": status.get("favourites_count", 0),
                "reposts": status.get("reblogs_count", 0),
                "replies": status.get("replies_count", 0),
            }

        if platform == "discord":
            if not DISCORD_WEBHOOK_URL:
                return None
            resp = requests.get(
                f"{DISCORD_WEBHOOK_URL}/messages/{platform_ref}",
                timeout=15,
            )
            resp.raise_for_status()
            message = resp.json()
            reactions = message.get("reactions", [])
            total_reactions = sum(r.get("count", 0) for r in reactions)
            return {"likes": total_reactions, "reposts": 0, "replies": 0}

        # telegram and anything else: not supported
        return None
    except (requests.RequestException, KeyError, ValueError):
        return None
