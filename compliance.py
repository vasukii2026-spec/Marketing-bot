"""
Compliance checker — flags language that's commonly problematic in crypto/
Web3 marketing (implied guaranteed returns, "financial advice"-adjacent
claims, high-pressure urgency, etc). This is NOT legal advice and doesn't
replace an actual compliance review — it's a first-pass net to catch
obviously risky phrasing before you hit approve.

Deliberately rule-based (regex), not an AI call: it's instant, free, and
predictable — the same input always gives the same flags, which matters
more here than nuance.
"""
import re

# Each entry: (pattern, human-readable reason, severity)
# severity: "high" = strongly reconsider before posting, "medium" = worth a second look
RISKY_PATTERNS = [
    (r"\bguarantee(d|s)?\b", "Implies guaranteed returns/outcomes — a major red flag for financial regulators.", "high"),
    (r"\brisk[\s-]?free\b", "\"Risk-free\" is essentially never accurate for a crypto asset and reads as a securities-law red flag.", "high"),
    (r"\bno risk\b", "Claiming \"no risk\" for a crypto asset is a common regulatory trigger phrase.", "high"),
    (r"\b\d+0{2,}x\b", "Specific multiplier claims (e.g. \"100x\", \"1000x\") read as unfounded return promises.", "high"),
    (r"\bcan'?t lose\b", "Implies a guaranteed positive outcome.", "high"),
    (r"\bsure(\s+|-)?(thing|bet|win)\b", "Implies a guaranteed outcome.", "high"),
    (r"\bdouble your (money|investment|coins?|tokens?)\b", "Specific return promise — high regulatory risk.", "high"),
    (r"\b(get|become)\s+rich\s+(quick|fast)\b", "Classic \"get rich quick\" phrasing, associated with scam patterns.", "high"),
    (r"\bfinancial advice\b", "If this claims to BE financial advice (rather than explicitly disclaiming it), that carries real regulatory obligations.", "medium"),
    (r"\binvestment advice\b", "Same issue as \"financial advice\" — check this isn't being framed as advice.", "medium"),
    (r"\b100%\s*(safe|secure|guaranteed)\b", "Absolute safety/certainty claims are rarely defensible for any crypto product.", "high"),
    (r"\bact now\b|\bdon'?t miss out\b|\blast chance\b|\bonly \d+ (left|spots?|slots?)\b", "High-pressure urgency language — not illegal, but worth a gut-check for tone.", "medium"),
    (r"\binsider (info|information|access|tip)\b", "\"Insider\" language can imply non-public information, which is a serious legal issue in traditional finance and increasingly scrutinized in crypto.", "high"),
    (r"\bpump\b", "\"Pump\" is closely associated with pump-and-dump schemes — likely to draw negative attention even if unintended.", "medium"),
    (r"\bmoon(ing)?\b|\bto the moon\b", "Common hype slang — not inherently risky, but worth knowing it's a recognized \"hype cycle\" signal.", "low"),
    (r"\bapprov(ed|al) by (the )?(sec|cftc|fca|government)\b", "Falsely implying government/regulator endorsement is a serious violation.", "high"),
    (r"\bregistered security\b|\bnot a security\b", "Making claims about legal/securities status is a substantive legal claim — should come from counsel, not marketing copy.", "medium"),
]

_COMPILED = [(re.compile(pattern, re.IGNORECASE), reason, severity) for pattern, reason, severity in RISKY_PATTERNS]


def check_content(content):
    """
    Returns a list of {"phrase": str, "reason": str, "severity": str} for
    every risky pattern found in the content. Empty list = nothing flagged.
    """
    if not content:
        return []
    flags = []
    for pattern, reason, severity in _COMPILED:
        match = pattern.search(content)
        if match:
            flags.append({
                "phrase": match.group(0),
                "reason": reason,
                "severity": severity,
            })
    # Highest severity first so the worst issues are visible without scrolling
    order = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda f: order.get(f["severity"], 3))
    return flags
