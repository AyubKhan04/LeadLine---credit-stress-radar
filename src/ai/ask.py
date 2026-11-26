"""'Ask the data' (phase 8): a question in any dashboard language, answered by
an AI model (Gemini free tier, or Claude) from a compact summary of the index. Needs GEMINI_API_KEY (free) or ANTHROPIC_API_KEY.

    python -m src.ai.ask "Which district was most stressed in 2021?"
"""
import sys
from functools import lru_cache

import pandas as pd

from src.config import PROCESSED
from src.ai.common import available, ask_ai  # noqa: F401  (available re-exported)

LANG_NAMES = {"en": "English", "ta": "Tamil", "hi": "Hindi", "te": "Telugu", "ml": "Malayalam", "kn": "Kannada"}


@lru_cache(maxsize=1)
def context() -> str:
    """Small enough to send every time (~6k tokens): yearly + last 12 months."""
    idx = pd.read_csv(PROCESSED / "stress_index_monthly.csv").dropna(subset=["stress_index"])
    idx["year"] = idx.month.str[:4]
    yearly = idx.groupby(["year", "district"]).stress_index.agg(["mean", "max"]).round(0)
    peak = idx.loc[idx.groupby(["year", "district"]).stress_index.idxmax(), ["year", "district", "month"]]
    recent = idx[idx.month >= sorted(idx.month.unique())[-12]][["district", "month", "stress_index", "band", "why"]]
    return ("Yearly mean/max index by district:\n" + yearly.to_csv()
            + "\nPeak month per year and district:\n" + peak.to_csv(index=False)
            + "\nLast 12 months:\n" + recent.to_csv(index=False))


def answer(question: str, lang: str = "en") -> str:
    system = ("You answer questions about the LeadLine Credit Stress Radar, a 0-100 index of household "
              "credit stress for Tamil Nadu districts built from public data (Google searches for pawning "
              "jewellery, rainfall, gold price, RBI repo rate, loan-app complaints, gold auction notices). "
              "Use only the data given. If it can't answer, say so. Keep it under 120 words. "
              f"Answer in {LANG_NAMES.get(lang, 'English')}.")
    return ask_ai(f"Data:\n{context()}\n\nQuestion: {question}", max_tokens=500, system=system)


if __name__ == "__main__":
    print(answer(" ".join(sys.argv[1:]) or "Which district is most stressed now?"))
