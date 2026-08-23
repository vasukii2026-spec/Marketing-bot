"""
Database models for Vasukii Marketing Bot.

Uses Postgres (works with Vercel Postgres / Neon / Supabase / any Postgres
connection string) instead of SQLite, because Vercel's serverless functions
have a read-only filesystem — a local .db file would not persist between
requests.

Behavior note: once a draft is successfully posted, its row is DELETED
(not kept around with status='posted'). This keeps the table from filling
up over time. The post_log table keeps a trimmed history (last 50 rows)
so "Recent Post Log" still works, but it also doesn't grow forever.
"""
import os
import psycopg2
import psycopg2.extras
from datetime import datetime
from contextlib import contextmanager

DATABASE_URL = (
    os.environ.get("DATABASE_URL")
    or os.environ.get("POSTGRES_URL")
    or os.environ.get("POSTGRES_URL_NON_POOLING")
)

POST_LOG_KEEP = 50


@contextmanager
def get_db():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set. Add a Postgres connection string "
            "(e.g. from Vercel Postgres / Neon) as the DATABASE_URL env var."
        )
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS drafts (
                id SERIAL PRIMARY KEY,
                platform TEXT NOT NULL,
                content TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
                created_at TEXT NOT NULL,
                posted_at TEXT,
                topic TEXT,
                media_path TEXT,   -- Vercel Blob URL, or NULL
                media_type TEXT    -- 'image' | 'video' | NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS post_log (
                id SERIAL PRIMARY KEY,
                draft_id INTEGER,
                platform TEXT NOT NULL,
                content TEXT NOT NULL,
                posted_at TEXT NOT NULL,
                success INTEGER NOT NULL,
                error_message TEXT
            )
        """)


def create_draft(platform, content, topic=None):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO drafts (platform, content, status, created_at, topic)
               VALUES (%s, %s, 'pending', %s, %s) RETURNING id""",
            (platform, content, datetime.utcnow().isoformat(), topic)
        )
        return cur.fetchone()["id"]


def get_drafts(status=None):
    with get_db() as conn:
        cur = conn.cursor()
        if status and status != "posted":
            cur.execute(
                "SELECT * FROM drafts WHERE status = %s ORDER BY created_at DESC", (status,)
            )
        elif status == "posted":
            # Posted drafts are deleted on success, so there's nothing to show here.
            # The Recent Post Log covers post history instead.
            return []
        else:
            cur.execute("SELECT * FROM drafts ORDER BY created_at DESC")
        return [dict(r) for r in cur.fetchall()]


def get_draft(draft_id):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM drafts WHERE id = %s", (draft_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def update_draft_content(draft_id, content):
    with get_db() as conn:
        conn.cursor().execute("UPDATE drafts SET content = %s WHERE id = %s", (content, draft_id))


def update_draft_media(draft_id, media_path, media_type):
    with get_db() as conn:
        conn.cursor().execute(
            "UPDATE drafts SET media_path = %s, media_type = %s WHERE id = %s",
            (media_path, media_type, draft_id)
        )


def clear_draft_media(draft_id):
    with get_db() as conn:
        conn.cursor().execute(
            "UPDATE drafts SET media_path = NULL, media_type = NULL WHERE id = %s", (draft_id,)
        )


def update_draft_status(draft_id, status):
    with get_db() as conn:
        conn.cursor().execute("UPDATE drafts SET status = %s WHERE id = %s", (status, draft_id))


def mark_posted(draft_id):
    """A post succeeded — delete the draft row entirely rather than keeping
    it around forever. This is what keeps the drafts table from filling up."""
    with get_db() as conn:
        conn.cursor().execute("DELETE FROM drafts WHERE id = %s", (draft_id,))


def delete_draft(draft_id):
    with get_db() as conn:
        conn.cursor().execute("DELETE FROM drafts WHERE id = %s", (draft_id,))


def log_post(draft_id, platform, content, success, error_message=None):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO post_log (draft_id, platform, content, posted_at, success, error_message)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (draft_id, platform, content, datetime.utcnow().isoformat(), int(success), error_message)
        )
        # Keep the log trimmed so it doesn't grow forever either.
        cur.execute("""
            DELETE FROM post_log WHERE id IN (
                SELECT id FROM post_log ORDER BY posted_at DESC OFFSET %s
            )
        """, (POST_LOG_KEEP,))


def get_post_log(limit=50):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM post_log ORDER BY posted_at DESC LIMIT %s", (limit,))
        return [dict(r) for r in cur.fetchall()]
