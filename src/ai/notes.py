"""Monthly credit note (phase 8). Run: python -m src.ai.notes [YYYY-MM]

Always writes a short rules-based English note. If ANTHROPIC_API_KEY is set, Claude
Haiku rewrites it as a readable analyst note in each dashboard language (one call
per language, about 6 calls a month, well under a cent each).
Output: data/processed/ai_notes.json  {month: {lang: text}}
"""
import json
import sys

import pandas as pd

from src.config import PROCESSED
from src.ai.common import available, ask_claude

LANG_NAMES = {"en": "English", "ta": "Tamil", "hi": "Hindi", "te": "Telugu", "ml": "Malayalam", "kn": "Kannada"}


def facts(month):
    idx = pd.read_csv(PROCESSED / "stress_index_monthly.csv")
    prev = (pd.Period(month, "M") - 1).strftime("%Y-%m")
    ly = (pd.Period(month, "M") - 12).strftime("%Y-%m")
    cur = idx[idx.month == month].set_index("district")
    p, y = idx[idx.month == prev].set_index("district"), idx[idx.month == ly].set_index("district")
    flags = pd.read_csv(PROCESSED / "anomaly_flags.csv") if (PROCESSED / "anomaly_flags.csv").exists() else pd.DataFrame()
    lines = []
    for d, r in cur.dropna(subset=["stress_index"]).iterrows():
        mom = r.stress_index - p.stress_index.get(d, float("nan"))
        yoy = r.stress_index - y.stress_index.get(d, float("nan"))
        lines.append(f"- {d}: {r.stress_index:.0f}/100 ({r.band}); vs last month {mom:+.0f}, vs a year ago {yoy:+.0f}. Why: {r.why}.")
    fl = flags[flags.month == month].detail.tolist() if len(flags) else []
    return lines, fl


def rules_note(month, lines, fl):
    head = f"Credit Stress Radar, {pd.Period(month, 'M').strftime('%B %Y')}. Index 0-100, higher means more stress."
    tail = ("Flags: " + "; ".join(fl[:6]) + ".") if fl else "No anomaly flags this month."
    return "\n".join([head, *lines, tail])


def main(month=None):
    idx = pd.read_csv(PROCESSED / "stress_index_monthly.csv").dropna(subset=["stress_index"])
    month = month or idx.month.max()
    lines, fl = facts(month)
    base = rules_note(month, lines, fl)
    path = PROCESSED / "ai_notes.json"
    notes = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    notes[month] = {"en": base, "_source": "rules"}
    if available():
        for code, name in LANG_NAMES.items():
            try:
                notes[month][code] = ask_claude(
                    f"Write a 120-word monthly credit stress note in {name} for a bank's risk team, "
                    f"from these facts only. Plain language, no hype, mention the biggest change and "
                    f"what to watch next month. Do not invent numbers.\n\n{base}", max_tokens=700)
                notes[month]["_source"] = "claude"
            except Exception as e:
                print(f"[notes] {code} failed: {e}")
    path.write_text(json.dumps(notes, ensure_ascii=False, indent=1), encoding="utf-8")
    print(notes[month].get("en"))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
