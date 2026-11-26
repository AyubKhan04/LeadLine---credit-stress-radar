"""Phase 5: district credit stress index, 0-100, with a "why" breakdown.

Each component becomes a 0-100 sub-score: the percentile of this month's value
against the district's own past (expanding window, so no peeking at the future;
the first 24 months are ranked against the first 24 months). The index is the
weighted mean of the sub-scores that exist that month; missing components drop
out and the rest are re-weighted. Each component's points (weight x sub-score)
are kept, so the "why" is just the biggest contributors.

Component choices come from docs/analysis.md (phase 4):
- rainfall leads pawn searches by about 4 months, and floods matter as well as
  drought, so rain stress is a two-tailed z-score (vs the same calendar month)
  averaged over this month and the 3 before
- seasonal series are compared year on year
"""
import numpy as np
import pandas as pd

from src.config import PROCESSED
from src.analysis.panel import build_panel

WEIGHTS = {  # visible on purpose; sums to 100
    "pawn_search": 30,     # Tamil searches for pawning jewellery, year-on-year
    "rain": 20,            # two-tailed rainfall anomaly, past 4 months
    "auctions": 20,        # gold auction accounts (only when notices exist)
    "digital_credit": 15,  # instant-loan / loan-app searches yoy + app complaints
    "rates": 10,           # repo rate level and recent hikes
    "gold_price": 5,       # falling gold prices push loans under water
}
LABELS = {
    "pawn_search": "people searching to pawn jewellery",
    "rain": "unusual rainfall (drought or flood) in recent months",
    "auctions": "gold loan auctions",
    "digital_credit": "demand for and complaints about instant loan apps",
    "rates": "higher interest rates",
    "gold_price": "falling gold prices",
}
BANDS = [(75, "Severe"), (60, "High"), (40, "Watch"), (0, "Low")]


def expanding_pct(x, min_hist=24):
    """Percentile (0-100) of each value among values up to and including it."""
    x = pd.Series(x).astype(float)
    out = pd.Series(np.nan, index=x.index)
    vals = x.values
    first = vals[:min_hist][~np.isnan(vals[:min_hist])]
    for i, v in enumerate(vals):
        if np.isnan(v):
            continue
        hist = vals[: i + 1][~np.isnan(vals[: i + 1])] if i >= min_hist else first
        if len(hist) < 6:
            continue
        out.iloc[i] = 100.0 * (np.sum(hist < v) + 0.5 * np.sum(hist == v)) / len(hist)
    return out


def raw_components(p):
    """District panel -> raw component values (higher = more stress)."""
    p = p.sort_values(["district", "month"]).copy()
    g = p.groupby("district")
    pawn = p[["trends_nagai_adagu", "trends_nagai_kadan"]].mean(axis=1)
    p["c_pawn_search"] = pawn - pawn.groupby(p.district).shift(12)
    # rainfall as a z-score against the same calendar month in that district, so a
    # dry January (normal ~40 mm) doesn't swamp the scale; both tails count
    cal = p.month.str[5:7]
    rz = p.groupby([p.district, cal]).rain_mm.transform(lambda v: (v - v.mean()) / v.std())
    p["c_rain"] = rz.abs().groupby(p.district).transform(lambda v: v.rolling(4, min_periods=2).mean())
    dig = p[["trends_instant_loan", "trends_loan_app"]].mean(axis=1)
    dig_yoy = dig - dig.groupby(p.district).shift(12)
    comp = p.app_complaint_share * 100
    p["c_digital_credit"] = np.where(comp.notna(), 0.5 * dig_yoy + 0.5 * (comp - comp.mean()), dig_yoy)
    hikes = g.repo_rate_change_bps.transform(lambda v: v.rolling(12, min_periods=1).sum())
    p["c_rates"] = p.repo_rate + hikes / 100
    p["c_gold_price"] = -p.gold_inr_yoy_pct
    p["c_auctions"] = pd.to_numeric(p.auction_accounts, errors="coerce")
    return p


def build_index(save=True):
    p = raw_components(build_panel(save=False))
    for c in WEIGHTS:
        p[f"score_{c}"] = p.groupby("district")[f"c_{c}"].transform(
            lambda v: expanding_pct(v, min_hist=6 if c == "auctions" else 24))
        if c == "auctions":  # too short for percentiles: scale vs district mean instead
            m = p.groupby("district").c_auctions.transform("mean")
            p["score_auctions"] = (50 * p.c_auctions / m).clip(0, 100)
    scores = p[[f"score_{c}" for c in WEIGHTS]]
    w = pd.Series({f"score_{c}": v for c, v in WEIGHTS.items()})
    avail = scores.notna().mul(w, axis=1)
    p["weight_used"] = avail.sum(axis=1)
    for c in WEIGHTS:  # points each component adds to the 0-100 index
        p[f"pts_{c}"] = (p[f"score_{c}"] * WEIGHTS[c] / p.weight_used).round(1)
    p["stress_index"] = p[[f"pts_{c}" for c in WEIGHTS]].sum(axis=1, min_count=1).round(1)
    p.loc[p.weight_used < 50, "stress_index"] = np.nan  # too little data to score
    p["band"] = p.stress_index.map(lambda v: next((b for t, b in BANDS if v >= t), None) if pd.notna(v) else None)
    p["why"] = p.apply(explain, axis=1)
    cols = (["district", "month", "stress_index", "band", "why", "weight_used"]
            + [f"score_{c}" for c in WEIGHTS] + [f"pts_{c}" for c in WEIGHTS])
    out = p[cols].round(1)
    if save:
        out.to_csv(PROCESSED / "stress_index_monthly.csv", index=False)
    return out


def explain(r):
    """Plain-English reason: components scoring well above their usual level."""
    if pd.isna(r.stress_index):
        return "not enough data"
    hot = sorted(((r[f"score_{c}"], c) for c in WEIGHTS if pd.notna(r[f"score_{c}"]) and r[f"score_{c}"] >= 65),
                 reverse=True)
    if not hot:
        return "all signals near or below normal"
    return "; ".join(f"{LABELS[c]} ({s:.0f}/100)" for s, c in hot[:3])


def backtest(idx):
    """Average index inside known stress episodes vs each district's normal."""
    from src.analysis.explore import EPISODES
    rows = []
    for name, a, b, where, why in EPISODES:
        b2 = (pd.Period(b, "M") + 1).strftime("%Y-%m")  # allow one month of lag
        x = idx[(idx.month >= a) & (idx.month <= b2)]
        if where != "all":
            x = x[x.district == where]
        rows.append(dict(episode=name, window=f"{a}..{b2}", where=where,
                         mean_index=round(x.stress_index.mean(), 1),
                         peak_index=round(x.stress_index.max(), 1),
                         months_high_or_worse=int((x.stress_index >= 60).sum()),
                         months_scored=int(x.stress_index.notna().sum())))
    bt = pd.DataFrame(rows)
    bt.to_csv(PROCESSED / "stress_index_backtest.csv", index=False)
    return bt


if __name__ == "__main__":
    idx = build_index()
    print(backtest(idx).to_string(index=False))
    latest = idx.dropna(subset=["stress_index"]).groupby("district").tail(1)
    print(latest[["district", "month", "stress_index", "band", "why"]].to_string(index=False))
    print(idx.groupby("district").stress_index.describe().round(1).to_string())
