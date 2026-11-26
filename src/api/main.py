"""Phase 6: credit stress score API.

Run:  uvicorn src.api.main:app --reload     then open http://127.0.0.1:8000/docs

Reads data/processed/stress_index_monthly.csv (built by src.index.stress_index).
"""
from functools import lru_cache
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from src.config import PROCESSED
from src.index.stress_index import WEIGHTS, LABELS, BANDS

app = FastAPI(title="LeadLine Credit Stress Radar API", version="1.0",
              description="District credit stress index for Tamil Nadu, 0-100, with reasons.")


@lru_cache(maxsize=1)
def data() -> pd.DataFrame:
    p = PROCESSED / "stress_index_monthly.csv"
    if not p.exists():
        raise RuntimeError("Run `python -m src.index.stress_index` first.")
    return pd.read_csv(p)


def _row(district: str, month: Optional[str]):
    d = data()
    rows = d[d.district.str.lower() == district.lower()].dropna(subset=["stress_index"])
    if rows.empty:
        raise HTTPException(404, f"Unknown district '{district}'. Try /districts.")
    if month:
        rows = rows[rows.month == month]
        if rows.empty:
            raise HTTPException(404, f"No score for {district} in {month}.")
    return rows.iloc[-1]


def _payload(r):
    comps = {c: {"label": LABELS[c], "weight": WEIGHTS[c],
                 "score": None if pd.isna(r[f"score_{c}"]) else round(float(r[f"score_{c}"]), 1),
                 "points": None if pd.isna(r[f"pts_{c}"]) else round(float(r[f"pts_{c}"]), 1)}
             for c in WEIGHTS}
    return {"district": r.district, "month": r.month, "stress_index": float(r.stress_index),
            "band": r.band, "why": r.why, "components": comps}


def band_of(v: float) -> str:
    return next(b for t, b in BANDS if v >= t)


@app.get("/health")
def health():
    d = data()
    return {"status": "ok", "rows": len(d), "latest_month": d.dropna(subset=["stress_index"]).month.max()}


@app.get("/districts")
def districts():
    d = data().dropna(subset=["stress_index"])
    latest = d.groupby("district").tail(1)
    return [{"district": r.district, "month": r.month, "stress_index": r.stress_index, "band": r.band}
            for r in latest.itertuples()]


@app.get("/score/{district}")
def score(district: str, month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$",
                                                      description="YYYY-MM; latest if omitted")):
    return _payload(_row(district, month))


@app.get("/history/{district}")
def history(district: str, start: str = "2019-01", end: str = "2100-12"):
    d = data()
    h = d[(d.district.str.lower() == district.lower()) & (d.month >= start) & (d.month <= end)]
    if h.empty:
        raise HTTPException(404, f"No history for '{district}'.")
    return h[["month", "stress_index", "band"]].astype(object).where(h.notna(), None).to_dict("records")


class WhatIf(BaseModel):
    district: str
    month: Optional[str] = None
    scores: dict[str, float] = Field(
        ..., description="Component -> new sub-score 0-100, e.g. {\"rain\": 90}",
        examples=[{"rain": 90, "gold_price": 80}])


@app.post("/whatif")
def whatif(req: WhatIf):
    """Re-score a district-month with some component sub-scores changed."""
    r = _row(req.district, req.month)
    bad = set(req.scores) - set(WEIGHTS)
    if bad:
        raise HTTPException(422, f"Unknown components {sorted(bad)}; use {list(WEIGHTS)}")
    s = {c: (req.scores[c] if c in req.scores else r[f"score_{c}"]) for c in WEIGHTS}
    s = {c: min(100.0, max(0.0, float(v))) for c, v in s.items() if pd.notna(v)}
    w = sum(WEIGHTS[c] for c in s)
    new = round(sum(s[c] * WEIGHTS[c] for c in s) / w, 1)
    return {"district": r.district, "month": r.month, "before": float(r.stress_index),
            "after": new, "band_after": band_of(new), "scores_used": s}
