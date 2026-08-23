"""
Login gate for the dashboard: a password plus a 6-digit TOTP code from an
authenticator app (Google Authenticator, Authy, 1Password, etc.) — the same
standard used for most "app-based 2FA" logins.

Setup (do this once):
1. Generate a TOTP secret:
     python -c "import pyotp; print(pyotp.random_base32())"
2. Put it in your env vars as TOTP_SECRET.
3. Put your chosen login password in ADMIN_PASSWORD.
4. Add that secret to your authenticator app. Easiest way: visit /setup-2fa
   on your running app (only works before you've scanned it once — see
   below) which shows the manual-entry key and account name to type into
   the app. Or construct the URI yourself:
     otpauth://totp/Vasukii%20Bot?secret=YOUR_SECRET&issuer=Vasukii
   and generate a QR code from it with any free QR generator to scan.

After that, every request needs: password + current 6-digit code from the
app before it can reach the dashboard.
"""
import os
import pyotp
from functools import wraps
from flask import session, request, redirect, url_for
from werkzeug.security import check_password_hash, generate_password_hash

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
TOTP_SECRET = os.environ.get("TOTP_SECRET", "")

# Precompute a hash of the password once, in memory, so we're not doing
# plaintext comparisons on every login attempt.
_PASSWORD_HASH = generate_password_hash(ADMIN_PASSWORD) if ADMIN_PASSWORD else None


def is_configured():
    return bool(ADMIN_PASSWORD and TOTP_SECRET)


def check_password(password):
    if not _PASSWORD_HASH:
        return False
    return check_password_hash(_PASSWORD_HASH, password)


def check_totp(code):
    if not TOTP_SECRET:
        return False
    totp = pyotp.TOTP(TOTP_SECRET)
    # valid_window=1 allows the code from 30s before/after, so a slightly
    # stale phone clock doesn't lock you out.
    return totp.verify(code.strip(), valid_window=1)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_configured():
            # Auth isn't set up — fail closed rather than silently open.
            return "Login is not configured. Set ADMIN_PASSWORD and TOTP_SECRET.", 503
        if not session.get("authed"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped
