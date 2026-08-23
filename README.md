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
   FLASK_SECRET_KEY=...          (any random string)
   ADMIN_PASSWORD=...            (the password you'll log in with)
   TOTP_SECRET=...               (see "Setting up login" below)
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
- There's still no background scheduler or auto-posting loop — every post
  only goes out the moment a human clicks Approve (or Retry) in the
  dashboard. "Automatic" here means "one click instead of two," not
  "unattended."
