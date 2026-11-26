"""Shared Claude client. Everything AI is optional: no ANTHROPIC_API_KEY, no calls."""
import os

MODEL = os.getenv("LEADLINE_AI_MODEL", "claude-haiku-5-5")  # cheapest model


def available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def ask_claude(prompt: str, max_tokens: int = 600, system: str = "") -> str:
    import anthropic
    msg = anthropic.Anthropic().messages.create(
        model=MODEL, max_tokens=max_tokens, system=system or anthropic.NOT_GIVEN,
        messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in msg.content if b.type == "text").strip()
