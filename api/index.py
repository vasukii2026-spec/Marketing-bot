"""
Vercel entrypoint. Vercel's Python runtime looks for a WSGI/ASGI app
object (or an `app.py` at the project root exporting one) inside /api.
This just re-exports the real Flask app from the project root.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import app  # noqa: E402

# Vercel's Python runtime calls this variable "app" (WSGI callable).
