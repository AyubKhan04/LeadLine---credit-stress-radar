"""Pluggable AI provider. Everything AI is optional.

Which provider runs (first match wins):
  LEADLINE_AI_PROVIDER=gemini|anthropic|none   force one
  GEMINI_API_KEY set                           Google Gemini, free tier (default choice)
  ANTHROPIC_API_KEY set                        Claude Haiku (paid, optional)
  neither                                      no AI: rule-based fallbacks only, costs nothing

Gemini's free tier needs no card. Google may use free-tier prompts to improve its
products and humans may review them, so text that could hold personal details
(OCR'd auction notices) is never sent to it; see `sensitive` below.
"""
import os
import time

import requests

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# "-latest" aliases follow Google's current Flash models; override with GEMINI_MODEL.
GEMINI_MODELS = [m for m in [os.getenv("GEMINI_MODEL"), "gemini-flash-lite-latest", "gemini-flash-latest"] if m]
ANTHROPIC_MODEL = os.getenv("LEADLINE_AI_MODEL", "claude-haiku-5-5")


def provider() -> str:
    forced = os.getenv("LEADLINE_AI_PROVIDER", "").lower()
    if forced in ("gemini", "anthropic", "none"):
        return forced
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "none"


def available(sensitive: bool = False) -> bool:
    """True if an AI call can be made. sensitive=True excludes Gemini's free tier."""
    p = provider()
    return p == "anthropic" or (p == "gemini" and not sensitive)


def ask_ai(prompt: str, system: str = "", max_tokens: int = 800, json_mode: bool = False) -> str:
    p = provider()
    if p == "gemini":
        return _gemini(prompt, system, max_tokens, json_mode)
    if p == "anthropic":
        return _anthropic(prompt, system, max_tokens)
    raise RuntimeError("No AI provider configured (set GEMINI_API_KEY for the free option).")


def _gemini(prompt, system, max_tokens, json_mode):
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.2}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    headers = {"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"}
    last = None
    for model in list(GEMINI_MODELS):
        for attempt in range(4):
            r = requests.post(GEMINI_URL.format(model=model), json=body, headers=headers, timeout=120)
            if r.status_code == 429:  # free-tier per-minute limit: wait and retry
                time.sleep(15 * (attempt + 1))
                continue
            if r.status_code == 404:  # model name retired: try the next one
                last = f"{model}: 404"
                GEMINI_MODELS.remove(model) if len(GEMINI_MODELS) > 1 else None
                break
            r.raise_for_status()
            parts = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
            return "".join(x.get("text", "") for x in parts).strip()
        else:
            last = f"{model}: rate limited"
    raise RuntimeError(f"Gemini failed ({last})")


def _anthropic(prompt, system, max_tokens):
    import anthropic
    msg = anthropic.Anthropic().messages.create(
        model=ANTHROPIC_MODEL, max_tokens=max_tokens, system=system or anthropic.NOT_GIVEN,
        messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in msg.content if b.type == "text").strip()


# kept for older imports
ask_claude = ask_ai
