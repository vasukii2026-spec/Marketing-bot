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
                status TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected | scheduled
                created_at TEXT NOT NULL,
                posted_at TEXT,
                topic TEXT,
                media_path TEXT,   -- Vercel Blob URL, or NULL
                media_type TEXT,   -- 'image' | 'video' | NULL
                scheduled_for TEXT -- ISO datetime, set when status = 'scheduled'
            )
        """)
        # Add scheduled_for if this table pre-dates the scheduling feature.
        cur.execute("""
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='drafts' AND column_name='scheduled_for'
                ) THEN
                    ALTER TABLE drafts ADD COLUMN scheduled_for TEXT;
                END IF;
            END $$;
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS post_log (
                id SERIAL PRIMARY KEY,
                draft_id INTEGER,
                platform TEXT NOT NULL,
                content TEXT NOT NULL,
                posted_at TEXT NOT NULL,
                success INTEGER NOT NULL,
                error_message TEXT,
                platform_ref TEXT,      -- message id / status id / AT-URI, for stats lookups
                likes INTEGER,
                reposts INTEGER,
                replies INTEGER,
                stats_checked_at TEXT
            )
        """)
        # Add columns if this table pre-dates this feature (safe no-op otherwise).
        for coltype in [
            "platform_ref TEXT", "likes INTEGER", "reposts INTEGER",
            "replies INTEGER", "stats_checked_at TEXT"
        ]:
            colname = coltype.split()[0]
            cur.execute(f"""
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='post_log' AND column_name='{colname}'
                    ) THEN
                        ALTER TABLE post_log ADD COLUMN {coltype};
                    END IF;
                END $$;
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


def schedule_draft(draft_id, scheduled_for_iso):
    with get_db() as conn:
        conn.cursor().execute(
            "UPDATE drafts SET status = 'scheduled', scheduled_for = %s WHERE id = %s",
            (scheduled_for_iso, draft_id)
        )


def unschedule_draft(draft_id):
    with get_db() as conn:
        conn.cursor().execute(
            "UPDATE drafts SET status = 'pending', scheduled_for = NULL WHERE id = %s",
            (draft_id,)
        )


def get_due_scheduled_drafts():
    """Scheduled drafts whose time has arrived (scheduled_for <= now)."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT * FROM drafts
               WHERE status = 'scheduled' AND scheduled_for <= %s
               ORDER BY scheduled_for ASC""",
            (datetime.utcnow().isoformat(),)
        )
        return [dict(r) for r in cur.fetchall()]


def mark_posted(draft_id):
    """A post succeeded — delete the draft row entirely rather than keeping
    it around forever. This is what keeps the drafts table from filling up."""
    with get_db() as conn:
        conn.cursor().execute("DELETE FROM drafts WHERE id = %s", (draft_id,))


def delete_draft(draft_id):
    with get_db() as conn:
        conn.cursor().execute("DELETE FROM drafts WHERE id = %s", (draft_id,))


def log_post(draft_id, platform, content, success, error_message=None, platform_ref=None):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO post_log (draft_id, platform, content, posted_at, success, error_message, platform_ref)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (draft_id, platform, content, datetime.utcnow().isoformat(), int(success), error_message, platform_ref)
        )
        new_id = cur.fetchone()["id"]
        # Keep the log trimmed so it doesn't grow forever either.
        cur.execute("""
            DELETE FROM post_log WHERE id IN (
                SELECT id FROM post_log ORDER BY posted_at DESC OFFSET %s
            )
        """, (POST_LOG_KEEP,))
        return new_id


def update_log_stats(log_id, likes, reposts, replies):
    with get_db() as conn:
        conn.cursor().execute(
            """UPDATE post_log SET likes = %s, reposts = %s, replies = %s, stats_checked_at = %s
               WHERE id = %s""",
            (likes, reposts, replies, datetime.utcnow().isoformat(), log_id)
        )


def get_post_log(limit=50):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM post_log ORDER BY posted_at DESC LIMIT %s", (limit,))
        return [dict(r) for r in cur.fetchall()]


def get_recent_contents(platform, limit=30):
    """Recent successfully-posted content for a platform, used by the
    duplicate-content guard to compare new drafts against."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT content FROM post_log
               WHERE platform = %s AND success = 1
               ORDER BY posted_at DESC LIMIT %s""",
            (platform, limit)
        )
        return [r["content"] for r in cur.fetchall()]


def get_calendar_data(days=45):
    """Returns {date_str: {"posted": n, "failed": n, "pending": n}} for the
    last `days` days, combining post_log (posted/failed) and drafts
    (pending — created but not yet acted on)."""
    with get_db() as conn:
        cur = conn.cursor()
        result = {}

        cur.execute("""
            SELECT substring(posted_at, 1, 10) AS day, success, COUNT(*) AS n
            FROM post_log
            WHERE posted_at >= (CURRENT_DATE - %s::int)::text
            GROUP BY day, success
        """, (days,))
        for row in cur.fetchall():
            day = row["day"]
            result.setdefault(day, {"posted": 0, "failed": 0, "pending": 0})
            if row["success"]:
                result[day]["posted"] += row["n"]
            else:
                result[day]["failed"] += row["n"]

        cur.execute("""
            SELECT substring(created_at, 1, 10) AS day, COUNT(*) AS n
            FROM drafts
            WHERE created_at >= (CURRENT_DATE - %s::int)::text
            GROUP BY day
        """, (days,))
        for row in cur.fetchall():
            day = row["day"]
            result.setdefault(day, {"posted": 0, "failed": 0, "pending": 0})
            result[day]["pending"] += row["n"]

        return result


def get_posts_for_day(day_str):
    """All post_log entries and drafts touching a specific YYYY-MM-DD day."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM post_log WHERE substring(posted_at,1,10) = %s ORDER BY posted_at DESC",
            (day_str,)
        )
        log_entries = [dict(r) for r in cur.fetchall()]
        cur.execute(
            "SELECT * FROM drafts WHERE substring(created_at,1,10) = %s ORDER BY created_at DESC",
            (day_str,)
        )
        drafts = [dict(r) for r in cur.fetchall()]
        return log_entries, drafts


def get_insights_data():
    """Aggregate data for the Insights dashboard: totals per platform,
    a 14-day daily post-count timeseries, and top posts by engagement."""
    with get_db() as conn:
        cur = conn.cursor()

        cur.execute("""
            SELECT platform, COUNT(*) AS total,
                   SUM(CASE WHEN success THEN 1 ELSE 0 END) AS succeeded,
                   COALESCE(SUM(likes), 0) AS likes,
                   COALESCE(SUM(reposts), 0) AS reposts,
                   COALESCE(SUM(replies), 0) AS replies
            FROM post_log
            GROUP BY platform
            ORDER BY total DESC
        """)
        by_platform = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT substring(posted_at, 1, 10) AS day, COUNT(*) AS n
            FROM post_log
            WHERE success = 1 AND posted_at >= (CURRENT_DATE - 14)::text
            GROUP BY day ORDER BY day ASC
        """)
        timeseries = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT platform, content, likes, reposts, replies, posted_at
            FROM post_log
            WHERE stats_checked_at IS NOT NULL
            ORDER BY (COALESCE(likes,0) + COALESCE(reposts,0) + COALESCE(replies,0)) DESC
            LIMIT 5
        """)
        top_posts = [dict(r) for r in cur.fetchall()]

        return {
            "by_platform": by_platform,
            "timeseries": timeseries,
            "top_posts": top_posts,
        }
