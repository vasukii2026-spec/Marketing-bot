# Vasukii Marketing Bot

A dashboard that generates marketing post drafts with a free AI (Groq —
hosted open-source models, not Claude/Google), lets you review and edit
them, then posts approved drafts to Discord, Bluesky, or Telegram.

This version is built to run on **Vercel**: drafts live in Postgres and
uploaded images/video live in Vercel Blob storage, instead of a local
SQLite file and a local uploads folder (Vercel's serverless functions
can't write to disk between requests, so those wouldn't have persisted).

Once a draft posts successfully, its row is deleted from the database
(and its uploaded file is deleted from Blob storage) instead of being
kept around forever — so the database doesn't just keep filling up.
The "Recent Post Log" below still shows your last 50 post attempts
(success or failure) for reference; older log entries get trimmed
automatically too.

## Deploying to Vercel

1. **Push this folder to a GitHub repo** (Vercel deploys from Git).

2. **Import the repo into Vercel**: vercel.com → Add New → Project →
   pick the repo. Leave the framework preset on "Other" — the included
   `vercel.json` tells Vercel how to build it.

3. **Add a Postgres database**: in your new Vercel project, go to the
   **Storage** tab → Create Database → Postgres (this is Vercel's
   Neon-backed Postgres, free tier is fine) → Connect to this project.
   Vercel automatically adds a `DATABASE_URL` (or `POSTGRES_URL`) env
   var — you don't need to copy/paste anything.

4. **Add Blob storage** (only needed if you'll attach images/video to
   posts): same Storage tab → Create Database → Blob → Connect to this
   project. Vercel adds `BLOB_READ_WRITE_TOKEN` automatically.

5. **Add your other env vars**: Project → Settings → Environment
   Variables. Add:
   ```
   GROQ_API_KEY=...
   DISCORD_WEBHOOK_URL=...
   BLUESKY_HANDLE=...            (optional)
   BLUESKY_APP_PASSWORD=...      (optional)
   TELEGRAM_BOT_TOKEN=...        (optional)
   TELEGRAM_CHAT_ID=...          (optional)
   MASTODON_INSTANCE=...         (optional, e.g. mastodon.social)
   MASTODON_ACCESS_TOKEN=...     (optional)
   FLASK_SECRET_KEY=...          (any random string)
   ADMIN_PASSWORD=...            (the password you'll log in with)
   TOTP_SECRET=...               (see "Setting up login" below)
   CRON_SECRET=...               (any random string, enables scheduled auto-generation)
   ```

6. **Deploy.** Vercel builds automatically on every push. Your dashboard
   will be live at the `*.vercel.app` URL Vercel gives you.

7. **First run**: the database tables are created automatically the
   first time the app starts (`models.init_db()` runs on import), so
   there's no manual migration step.

## Setting up login (password + 2FA)

Anyone who gets the URL only gets a login screen — the dashboard itself
requires a password *and* a 6-digit code from an authenticator app
(Google Authenticator, Authy, 1Password, etc.), the same style of 2FA
used by most bank/email logins. Set it up once:

1. **Pick a password** and set it as `ADMIN_PASSWORD` in your env vars.
2. **Generate a 2FA secret** — run this once, anywhere with Python:
   ```
   python -c "import pyotp; print(pyotp.random_base32())"
   ```
   It prints something like `JBSWY3DPEHPK3PXP`. Set that as `TOTP_SECRET`
   in your env vars.
3. **Add it to your authenticator app**: open Google Authenticator (or
   similar) → Add account → "Enter a setup key manually" → account name
   can be anything (e.g. "Vasukii Bot") → paste the same secret from
   step 2 → Time-based. The app will now show a fresh 6-digit code every
   30 seconds.
4. **Log in**: open your dashboard URL, enter your password plus the
   current 6-digit code from the app.

Notes:
- If `ADMIN_PASSWORD` or `TOTP_SECRET` aren't set, the app refuses all
  dashboard requests (fails closed) rather than leaving it open.
- Sessions last 7 days, so you won't have to log in on every visit.
- To change your password or reset 2FA, just update the env vars and
  redeploy — this immediately invalidates the old ones. If you change
  `TOTP_SECRET`, you'll need to re-add the new secret to your
  authenticator app too.

## Local setup (optional, for testing before you deploy)

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Get your keys

- **Groq API key** (free): go to https://console.groq.com/keys, sign up, click
  "Create API Key," copy it.
- **Discord webhook URL**: in your Discord server, go to Server Settings →
  Integrations → Webhooks → New Webhook, pick a channel, click "Copy Webhook
  URL."
- **Bluesky app password** (free, optional — only if you want to post to
  Bluesky): log into your Bluesky account → Settings → Privacy and Security
  → App Passwords → Add App Password. Copy it immediately, you can't view
  it again after closing the dialog. This is separate from your real login
  password.
- **Telegram bot token** (free, optional — only if you want to post to
  Telegram): message @BotFather in Telegram, send `/newbot`, follow the
  prompts. Add the resulting bot as an admin of the channel you want to
  post to, then get that channel's chat id (its `@handle` if public, or
  the numeric id from `getUpdates` if private — see
  `connectors/telegram_connector.py` for the exact steps).

### 3. Paste your keys into the `.env` file

1. In this folder, find the file named `.env.example`
2. Make a copy of it and rename the copy to exactly `.env` (no ".example")
3. Open `.env` in Notepad and paste your keys in:
   ```
   GROQ_API_KEY=gsk_your_actual_key_here
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your_actual_url_here
   BLUESKY_HANDLE=yourname.bsky.social
   BLUESKY_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
   TELEGRAM_BOT_TOKEN=123456789:AAF...
   TELEGRAM_CHAT_ID=@yourchannelname
   ```
   (Skip whichever platform's lines you're not using yet.)
4. Save and close the file.

The bot reads this file automatically every time it starts — you only have
to do this once, not every session.

### 4. Run it
```bash
python app.py
```
Open **http://localhost:5000** in your browser.

## How to use

1. **Generate** — pick a platform (Discord, Bluesky, or Telegram), type a
   topic ("VAK airdrop reminder", "50k claims milestone"), choose how many
   variants, click Generate.
2. **Review** — drafts appear under "Pending." Edit the text inline if
   needed.
3. **Approve & Post** — clicking Approve immediately sends the post to its
   platform. One click, no separate "Post Now" step.
   - If it succeeds, the draft moves to "Posted."
   - If it fails (bad credentials, network issue, over a length limit,
     etc.), it stays visible with a "Retry Post" button and the error shows
     in the Recent Post Log below.
4. **Reject** — discards a draft without posting it.

## Notes

- Uses Postgres for drafts/log and Vercel Blob for uploaded media — both
  required in production (see Deploying to Vercel above). Locally, point
  `DATABASE_URL` at any Postgres instance (a free Neon database works fine
  even if you're not deploying yet).
- **Posted drafts are deleted, not archived.** Once a post succeeds, its
  row is removed from the drafts table and its media file is removed from
  Blob storage. If you want a permanent record of what was posted, that's
  the "Recent Post Log" list (kept as the last 50 entries) — not the
  drafts table.
- The content generator (`generator.py`) has Vasukii's branding, tone, and
  feature list baked into the prompt — edit `VASUKII_CONTEXT` there if
  anything changes (new features, updated airdrop numbers, etc).

## Platforms

Discord, Bluesky, Telegram, and **Mastodon** are wired up — all free, no
paid API tier, no app-review wait. X/Twitter and Instagram were
deliberately skipped: X now charges per post with no free tier, and
Instagram's Graph API requires a multi-week Meta app review process
before it'll post on your behalf. Reddit is effectively closed to new
developers as of 2026. If any of those change, the connector pattern in
`connectors/` is easy to extend.

## Features

- **Multiple draft variations** — generate 1/3/5 versions of a post per
  topic (the "Variants" dropdown) and pick the best one.
- **Tone presets** — Default / Hype / Educational / Casual, applied to
  the generation prompt.
- **Duplicate-content guard** — new drafts are compared against the last
  30 successful posts on that platform; anything too similar is skipped
  automatically and you're told how many were filtered out.
- **Post performance tracking** — click "🔄 Refresh stats" in the Recent
  Post Log to pull current like/repost/reply counts for Bluesky,
  Mastodon, and Discord posts (all via public read endpoints, no extra
  auth needed). Telegram doesn't expose this data via its Bot API, so
  those rows just show "n/a".
- **Scheduled auto-generation** — a Vercel Cron job hits
  `/api/cron/auto-generate` once a day (see `vercel.json`), which
  generates one new PENDING draft on a rotating topic/platform. Nothing
  posts automatically — every draft still needs a human click to go
  live. Set `CRON_SECRET` in your env vars (any random string); Vercel
  automatically sends it as the request's Bearer token, no extra wiring
  needed. Customize the topic list with the `AUTO_TOPICS` env var
  (comma-separated), or edit `DEFAULT_AUTO_TOPICS` in `generator.py`.
  Note: Vercel's Hobby plan allows cron jobs but caps them to daily
  scheduling — that's already what's configured.
- There's still no unattended auto-*posting* — "automatic" here means
  drafts appear on their own; a human still approves before anything
  goes out.
- **AI image generation** — click "🎨 Generate image" on any draft. Leave
  the text box blank and Groq writes an image description from the
  post's content automatically (in Vasukii's cosmic/serpent visual
  style); or type your own description to use instead. The actual image
  comes from Pollinations.ai — a free, no-key, no-signup image
  generation service (Groq itself can't generate images, only text — this
  is a separate provider). Takes ~10-20 seconds. No cost either way.
- **Hashtag suggestions** — click "💡 Suggest hashtags" on any draft to
  get 3-5 AI-suggested tags (crypto/web3-tuned); click any chip to append
  it to the draft. Uses your existing Groq key, no extra setup.
- **Character-count preview** — a live counter under each draft's text
  box, colored red if you're over that platform's limit (Bluesky 300,
  Mastodon 500, Telegram 4096, Discord's soft ceiling 2000).
- **Calendar view** (`/calendar`, linked from the top bar) — see the last
  45 days at a glance: posted/failed/drafted counts per day, click into
  any day for details.
- **Insights dashboard** (`/insights`, linked from the top bar) — charts
  for posts-per-platform, total engagement per platform, a 14-day
  posting timeseries, and your top 5 posts by engagement. Engagement
  numbers only populate for posts you've refreshed stats on (see "Post
  performance tracking" above) — it's not live/real-time.

## Scheduling posts for a specific time

Each pending draft has a "🕐 Schedule (UTC)" field — pick a date/time and
it moves to the **Scheduled** tab instead of posting immediately. When
that time arrives, `/api/cron/check-scheduled` posts it automatically
(no human click needed at that point — only the *scheduling* decision
was manual).

**Important — this needs a bit of extra setup beyond just deploying:**
Vercel's own Cron on the Hobby plan only fires once a day, and even then
only "sometime within the scheduled hour" — not useful for "post this at
2:37pm." To get real time-of-day precision for free, point a free
external scheduler at that route instead:

1. Sign up for a free account at [cron-job.org](https://cron-job.org)
   (or any similar free cron service).
2. Create a new cron job:
   - URL: `https://your-app.vercel.app/api/cron/check-scheduled`
   - Schedule: every 5 minutes (or however precise you want it)
   - Method: POST
   - Add a custom header: `Authorization: Bearer YOUR_CRON_SECRET`
     (same value as your `CRON_SECRET` env var in Vercel)
3. That's it — the route checks for any scheduled draft whose time has
   passed and posts it, every time it's hit.

**Times are UTC.** The schedule field doesn't do timezone conversion —
whatever you type is treated as UTC. If you're not in UTC, do the math
once (e.g. IST is UTC+5:30, so 7:00 PM IST = 1:30 PM UTC) or just note
your offset and always add/subtract it when scheduling.

The daily Vercel Cron already in `vercel.json` still runs for
auto-generation — you don't need to remove it. This external scheduler
is *only* for checking scheduled posts more often than once a day.

## Compliance checker (risky language flagging)

A "⚠ Flagged for review" box automatically appears on any draft
containing language that's commonly risky in crypto/Web3 marketing —
things like "guaranteed returns," "risk-free," "100x," "get rich quick,"
implied regulatory approval, and similar phrases. It runs instantly,
locally, for free (no AI call — it's a pattern-matching check, not a
Groq request), both right after generation and live on every draft
render, so edits get re-checked too.

**This is a first-pass net, not legal advice or a compliance
guarantee.** It catches obviously risky phrasing; it won't catch every
subtle issue, and a false positive (flagging something that's actually
fine, like "this is not financial advice") is possible. Treat it as a
prompt to double-check, not a stamp of approval. If Vasukii's marketing
needs real regulatory sign-off, that still means an actual compliance
review — this tool doesn't replace one.

To adjust what's flagged, edit `RISKY_PATTERNS` in `compliance.py` — add,
remove, or reword entries; each has a regex pattern, a plain-English
reason, and a severity (`high`/`medium`/`low`).
