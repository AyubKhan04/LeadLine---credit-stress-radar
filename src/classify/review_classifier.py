"""Label loan-app reviews as credit-stress complaints.

Step 1 (always): keyword rules in English, Tamil script and common Tanglish.
Step 2 (optional): if ANTHROPIC_API_KEY is set, low-star reviews that no rule
matched are sent in small batches to Claude Haiku. Capped per run to keep cost
to cents.
"""
import json
import os
import re

LABELS = ["harassment", "threats", "hidden_charges", "recovery_agents", "fraud"]

RULES = {
    "harassment": [
        r"harass", r"torture", r"abus(e|ive|ing)", r"insult", r"humiliat", r"mental(ly)? (torture|pressure)",
        r"call(ing|ed|s)? (my )?(family|relatives|friends|contacts|parents|office|colleagues)",
        r"contact list", r"access(ed)? (my )?contacts", r"morph", r"vulgar", r"bad words",
        r"தொல்லை", r"டார்ச்சர்", r"அசிங்க", r"கேவலம", r"திட்டு",
    ],
    "threats": [
        r"threat", r"blackmail", r"legal action", r"police case", r"(?-i:\bFIR\b)", r"arrest",
        r"viral", r"defam", r"photos? (to|with)", r"suicide",
        r"மிரட்ட", r"மிரட்டல்", r"போலீஸ்", r"தற்கொலை", r"mirat",
    ],
    "hidden_charges": [
        r"hidden (charge|fee|cost)", r"processing fee", r"extra charge", r"high interest",
        r"interest (rate )?(is )?(too|very) high", r"deduct", r"\bgst\b", r"insurance (charge|fee|added)",
        r"late fee", r"penalty", r"less amount", r"received only", r"charged (me )?(extra|more)",
        r"கட்டணம்", r"வட்டி அதிக", r"அதிக வட்டி", r"கழித்து", r"மறைமுக",
    ],
    "recovery_agents": [
        r"recovery (agent|team|call)", r"collection (agent|team|call)", r"agents? (call|came|visit)",
        r"(\d+|many|continuous(ly)?|repeated(ly)?) calls", r"calls? (every|daily|day and night)",
        r"வசூல்", r"ஏஜென்ட்",
    ],
    "fraud": [
        r"\bfraud", r"\bscam", r"cheat", r"fake (app|company|loan)", r"loan (not|never) (received|disbursed|credited)",
        r"without (my )?(consent|permission|applying)", r"மோசடி", r"ஏமாற்ற", r"ஏமாத்",
    ],
}
_COMPILED = {k: [re.compile(p, re.I) for p in v] for k, v in RULES.items()}
_TAMIL = re.compile(r"[஀-௿]")


def language(text: str) -> str:
    return "ta" if _TAMIL.search(text or "") else "en"


def rule_labels(text: str, rating: int | None = None) -> list[str]:
    """Keyword labels. 4-5 star reviews are never counted as complaints
    (they mention "fraud" mostly to praise the app as not being one)."""
    if rating is not None and rating >= 4:
        return []
    t = text or ""
    return [k for k, pats in _COMPILED.items() if any(p.search(t) for p in pats)]


SYSTEM = (
    "You label Indian loan-app store reviews (English, Tamil or Tanglish). "
    f"For each review return the labels that apply from: {', '.join(LABELS)}. "
    "harassment = abusive or shaming contact, contacting family/friends; threats = legal, police, "
    "defamation or other threats; hidden_charges = undisclosed fees, deductions, very high interest; "
    "recovery_agents = aggressive collection calls or visits; fraud = scam, loan not disbursed, "
    "money taken without consent. Return an empty list if none apply (e.g. app bugs, KYC issues)."
)
SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "i": {"type": "integer"},
                    "labels": {"type": "array", "items": {"type": "string", "enum": LABELS}},
                },
                "required": ["i", "labels"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}


def ai_labels(texts: list[str], batch_size: int = 20) -> list[list[str]] | None:
    """Return labels per text, or None if no API key is configured."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    import anthropic

    client = anthropic.Anthropic()
    model = os.getenv("LEADLINE_AI_MODEL", "claude-haiku-5-5")
    out: list[list[str]] = [[] for _ in texts]
    for start in range(0, len(texts), batch_size):
        chunk = texts[start:start + batch_size]
        listing = "\n".join(f"[{i}] {t[:600]}" for i, t in enumerate(chunk))
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=2048,
                system=SYSTEM,
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
                messages=[{"role": "user", "content": listing}],
            )
        except anthropic.APIStatusError as e:
            print(f"[ai] batch {start} failed: {e.status_code} {e.message}")
            continue
        except anthropic.APIConnectionError as e:
            print(f"[ai] batch {start} connection error: {e}")
            continue
        if resp.stop_reason != "end_turn":
            print(f"[ai] batch {start} stopped: {resp.stop_reason}")
            continue
        text = next(b.text for b in resp.content if b.type == "text")
        for r in json.loads(text)["results"]:
            if 0 <= r["i"] < len(chunk):
                out[start + r["i"]] = r["labels"]
    return out
