"""
Vasukii Marketing Bot — Web Dashboard

Run with: python app.py
Then open http://localhost:5000
"""
import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

load_dotenv()  # reads keys from the .env file so you don't set them in the terminal each time

import models
import generator
import storage
import auth
import stats
from connectors.discord_connector import post_to_discord
from connectors.bluesky_connector import post_to_bluesky
from connectors.telegram_connector import post_to_telegram
from connectors.mastodon_connector import post_to_mastodon

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "vasukii-dev-secret-change-me")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("VERCEL", "") != "",  # HTTPS-only cookie in production
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 7,  # stay logged in for 7 days
)
models.init_db()

IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp"}
VIDEO_EXTS = {"mp4", "mov", "webm"}

PUBLISHERS = {
    "discord": post_to_discord,
    "bluesky": post_to_bluesky,
    "telegram": post_to_telegram,
    "mastodon": post_to_mastodon,
}

DUPLICATE_SIMILARITY_THRESHOLD = 0.82


def _media_type_for(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    return None


def _is_duplicate(new_content, recent_contents):
    """True if new_content is suspiciously similar to anything already
    posted recently — a lightweight guard against accidentally repeating
    yourself. Uses stdlib difflib, no extra dependency."""
    import difflib
    for existing in recent_contents:
        ratio = difflib.SequenceMatcher(None, new_content, existing).ratio()
        if ratio >= DUPLICATE_SIMILARITY_THRESHOLD:
            return True
    return False


def _publish(draft_id, platform, content, media_path=None, media_type=None):
    """Send a draft to its platform, log the attempt, and update its status."""
    publisher = PUBLISHERS.get(platform)
    if publisher:
        success, error, platform_ref = publisher(content, media_path=media_path, media_type=media_type)
    else:
        success, error, platform_ref = False, f"Posting to '{platform}' isn't wired up yet.", None

    models.log_post(draft_id, platform, content, success, error, platform_ref=platform_ref)
    if success:
        # Delete any attached blob too, so storage doesn't fill up with
        # media from posts that already went out.
        if media_path:
            storage.delete_url(media_path)
        models.mark_posted(draft_id)  # deletes the draft row
    else:
        # Leave it in "approved" so the failure is visible and Post Now can retry it.
        models.update_draft_status(draft_id, "approved")
    return success, error


@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.values.get("next") or url_for("dashboard")
    if request.method == "GET":
        return render_template("login.html", next=next_url)

    password = request.form.get("password", "")
    code = request.form.get("code", "")

    if not auth.is_configured():
        flash("Login is not configured on the server (missing ADMIN_PASSWORD / TOTP_SECRET).", "error")
        return render_template("login.html", next=next_url), 503

    if auth.check_password(password) and auth.check_totp(code):
        session.clear()
        session["authed"] = True
        session.permanent = True
        return redirect(next_url)

    flash("Incorrect password or code.", "error")
    return render_template("login.html", next=next_url), 401


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@auth.login_required
def dashboard():
    status_filter = request.args.get("status", "pending")
    if status_filter == "all":
        drafts = models.get_drafts()
    else:
        drafts = models.get_drafts(status=status_filter)
    log = models.get_post_log(limit=20)
    return render_template("dashboard.html", drafts=drafts, log=log, current_filter=status_filter)


@app.route("/generate", methods=["POST"])
@auth.login_required
def generate():
    platform = request.form.get("platform", "discord")
    topic = request.form.get("topic", "").strip()
    count = int(request.form.get("count", 3))
    tone = request.form.get("tone", "default")

    if not topic:
        flash("Topic is required.", "error")
        return redirect(url_for("dashboard"))

    try:
        variants = generator.generate_variants(platform, topic, count=count, tone=tone)
    except Exception as e:
        flash(f"Generation failed: {e}", "error")
        return redirect(url_for("dashboard"))

    recent = models.get_recent_contents(platform, limit=30)
    created, skipped = 0, 0
    for v in variants:
        if _is_duplicate(v, recent):
            skipped += 1
            continue
        models.create_draft(platform, v, topic=topic)
        created += 1

    if skipped:
        flash(
            f"Generated {created} draft(s) — skipped {skipped} that looked too similar "
            f"to something posted recently.",
            "info" if created else "error",
        )

    return redirect(url_for("dashboard"))


@app.route("/draft/<int:draft_id>/edit", methods=["POST"])
@auth.login_required
def edit_draft(draft_id):
    new_content = request.form.get("content", "").strip()
    if new_content:
        models.update_draft_content(draft_id, new_content)
    return redirect(url_for("dashboard"))


@app.route("/draft/<int:draft_id>/media", methods=["POST"])
@auth.login_required
def upload_media(draft_id):
    draft = models.get_draft(draft_id)
    if not draft:
        return jsonify({"error": "Draft not found"}), 404

    file = request.files.get("media")
    if not file or file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    media_type = _media_type_for(file.filename)
    if not media_type:
        return jsonify({"error": "Unsupported file type. Use png/jpg/gif/webp for images or mp4/mov/webm for video."}), 400

    ext = file.filename.rsplit(".", 1)[-1].lower()
    filename = secure_filename(f"{draft_id}_{uuid.uuid4().hex[:8]}.{ext}")

    try:
        blob_url = storage.upload_bytes(file.read(), filename, file.mimetype or "application/octet-stream")
    except Exception as e:
        return jsonify({"error": f"Upload failed: {e}"}), 500

    models.update_draft_media(draft_id, blob_url, media_type)
    return redirect(url_for("dashboard"))


@app.route("/draft/<int:draft_id>/media/remove", methods=["POST"])
@auth.login_required
def remove_media(draft_id):
    draft = models.get_draft(draft_id)
    if draft and draft.get("media_path"):
        storage.delete_url(draft["media_path"])
    models.clear_draft_media(draft_id)
    return redirect(url_for("dashboard"))


@app.route("/draft/<int:draft_id>/approve", methods=["POST"])
@auth.login_required
def approve_draft(draft_id):
    """Approving now posts immediately — one click instead of Approve + Post Now.
    If the post fails (bad creds, network, etc.) it stays visible as 'approved'
    with the error shown, and Post Now becomes a manual retry button."""
    draft = models.get_draft(draft_id)
    if not draft:
        return jsonify({"error": "Draft not found"}), 404

    _publish(draft_id, draft["platform"], draft["content"], draft.get("media_path"), draft.get("media_type"))
    return redirect(url_for("dashboard"))


@app.route("/draft/<int:draft_id>/reject", methods=["POST"])
@auth.login_required
def reject_draft(draft_id):
    models.update_draft_status(draft_id, "rejected")
    return redirect(url_for("dashboard"))


@app.route("/draft/<int:draft_id>/post", methods=["POST"])
@auth.login_required
def post_draft(draft_id):
    """Manual retry for a draft that failed to post on approve."""
    draft = models.get_draft(draft_id)
    if not draft:
        return jsonify({"error": "Draft not found"}), 404

    _publish(draft_id, draft["platform"], draft["content"], draft.get("media_path"), draft.get("media_type"))
    return redirect(url_for("dashboard"))


@app.route("/stats/refresh", methods=["POST"])
@auth.login_required
def refresh_stats():
    """Pulls current like/repost/reply counts for recent posted entries,
    where the platform supports public lookups (Bluesky, Mastodon,
    Discord). Telegram entries are silently skipped (not supported)."""
    log = models.get_post_log(limit=50)
    updated = 0
    for entry in log:
        if not entry.get("success") or not entry.get("platform_ref"):
            continue
        result = stats.fetch_stats(entry["platform"], entry["platform_ref"])
        if result:
            models.update_log_stats(
                entry["id"], result["likes"], result["reposts"], result["replies"]
            )
            updated += 1
    flash(f"Refreshed stats for {updated} post(s).", "info")
    return redirect(url_for("dashboard"))


@app.route("/api/cron/auto-generate", methods=["GET", "POST"])
def cron_auto_generate():
    """Scheduled auto-generation, triggered by Vercel Cron (see vercel.json).
    Creates new PENDING drafts on a rotating topic/platform — nothing
    posts automatically, a human still has to approve every draft.

    Protected by CRON_SECRET so randoms can't trigger generation (and burn
    your Groq quota) by hitting this URL.
    """
    cron_secret = os.environ.get("CRON_SECRET", "")
    auth_header = request.headers.get("Authorization", "")
    if not cron_secret or auth_header != f"Bearer {cron_secret}":
        return jsonify({"error": "unauthorized"}), 401

    import random
    topics = generator.get_auto_topics()
    if not topics:
        return jsonify({"created": 0, "note": "no topics configured"}), 200

    platform = random.choice(list(PUBLISHERS.keys()))
    topic = random.choice(topics)

    try:
        variants = generator.generate_variants(platform, topic, count=1)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    recent = models.get_recent_contents(platform, limit=30)
    created = 0
    for v in variants:
        if _is_duplicate(v, recent):
            continue
        models.create_draft(platform, v, topic=f"[auto] {topic}")
        created += 1

    return jsonify({"created": created, "platform": platform, "topic": topic}), 200


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
