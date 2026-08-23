"""
Content generator using Groq's free API (hosted open-source models —
Llama 3 / Mixtral). Not Claude, not Google — fits the 'own AI' requirement
while staying free and requiring no local hardware.

Get a free API key at: https://console.groq.com/keys
"""
import os
import requests

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-20b"  # fast + free-tier friendly (Groq's current recommended model)

VASUKII_CONTEXT = """
You are writing marketing content for Vasukii (vasukii.xyz), a wallet-native
Web3 social app on Polygon. Its dark cosmic-void/serpent aesthetic and features:
- AES-256 encrypted, token-gated chat rooms
- Threads: Twitter-style feed with wallet-verified tipping
- End-to-end encrypted DMs (ECDH)
- File shredding vault
- Daily game/presale mechanics
- VAK token airdrop: currently LIVE, direct claim, no waitlist, no snapshot
  delay, targeting 100,000 claims. Contract: 0x3f94Fd0959aa9e9620895571FDde2561B30554dE

Tone: confident, a little mysterious/cosmic, crypto-native voice. Avoid
hype-scam language ("guaranteed", "1000x").
Always include vasukii.xyz as the call to action link.
"""

DISCORD_RULE = "Write a Discord announcement. Can be slightly longer, use a header line, and can include markdown formatting like **bold**."
BLUESKY_RULE = "Write a Bluesky post. Keep it under 300 characters. Punchy and conversational, minimal hashtags."
TELEGRAM_RULE = "Write a Telegram channel announcement. Can be a bit longer than a tweet, plain text (no markdown symbols), can include emojis, ends with a clear call to action."

PLATFORM_RULES = {
    "discord": DISCORD_RULE,
    "bluesky": BLUESKY_RULE,
    "telegram": TELEGRAM_RULE,
}


def generate_draft(platform, topic):
    """
    Generate a single marketing draft for the given platform and topic.
    Returns the generated text, or raises an exception on API failure.
    """
    if not GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY not set. Get a free key at https://console.groq.com/keys "
            "and set it as an environment variable."
        )

    prompt = f"""{VASUKII_CONTEXT}

Task: {PLATFORM_RULES.get(platform, DISCORD_RULE)}
Topic/angle: {topic}

Write only the post content. No preamble, no explanation, no quotation marks around it."""

    response = requests.post(
        GROQ_URL,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.8,
            "max_completion_tokens": 1200,
            "reasoning_effort": "low",   # this model "thinks" before answering — low
                                         # effort keeps the reasoning short so tokens
                                         # are left for the actual post content
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    message = data["choices"][0]["message"]
    content = (message.get("content") or "").strip()

    if not content:
        # The model spent its whole token budget on internal reasoning and left
        # nothing for the actual answer — surface a clear error instead of a
        # blank draft.
        raise RuntimeError(
            "Groq returned an empty response (likely spent its token budget on "
            "internal reasoning). Try again — if it keeps happening, lower "
            "reasoning_effort further or raise max_completion_tokens in generator.py."
        )
    return content


def generate_variants(platform, topic, count=3):
    """Generate multiple draft variants for the same topic."""
    return [generate_draft(platform, topic) for _ in range(count)]
