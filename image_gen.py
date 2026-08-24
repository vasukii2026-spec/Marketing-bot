"""
Free image generation via Pollinations.ai — no API key, no signup, no
cost. Works by hitting a URL with the description baked in; the response
body is the image itself.

This does NOT use Groq (Groq can only generate text) — it's a completely
separate, free service. Groq is used elsewhere (see generator.py) only to
*write* the image description that gets sent here.
"""
import random
import urllib.parse
import requests

POLLINATIONS_BASE = "https://image.pollinations.ai/prompt/"


def generate_image_bytes(prompt, width=1024, height=1024, timeout=60):
    """
    Generates an image from a text description via Pollinations' free API.
    Returns (image_bytes, source_url).
    Raises requests.RequestException on failure (network issue, service
    briefly down, etc — Pollinations has no uptime guarantee since it's free).
    """
    encoded_prompt = urllib.parse.quote(prompt)
    # A random seed avoids getting a cached/identical image if the same
    # prompt is used twice.
    seed = random.randint(0, 999_999)
    url = (
        f"{POLLINATIONS_BASE}{encoded_prompt}"
        f"?width={width}&height={height}&seed={seed}&nologo=true"
    )
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.content, url
