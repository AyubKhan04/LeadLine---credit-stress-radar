"""Anomaly flags (phase 8): rules, no AI. Run: python -m src.ai.anomaly

Flags a district-month when
- the index jumps 15+ points in a month, or crosses into High/Severe
- any component scores 90+ (top tenth of its own history)
- a raw signal is 3+ robust z-scores from its district median (median/MAD)
Writes data/processed/anomaly_flags.csv
"""
import pandas as pd

from src.config import PROCESSED
from src.index.stress_index import WEIGHTS, LABELS

RAW = {"rain_mm": "rainfall", "trends_nagai_adagu": "pawn searches", "trends_gold_loan": "gold loan searches",
       "trends_instant_loan": "instant loan searches", "auction_accounts": "auction accounts"}


def flags():
    idx = pd.read_csv(PROCESSED / "stress_index_monthly.csv").sort_values(["district", "month"])
    panel = pd.read_csv(PROCESSED / "panel_monthly.csv")
    out = []
    idx["prev"] = idx.groupby("district").stress_index.shift()
    idx["prev_band"] = idx.groupby("district").band.shift()
    for r in idx.dropna(subset=["stress_index"]).itertuples():
        if pd.notna(r.prev) and r.stress_index - r.prev >= 15:
            out.append((r.district, r.month, "index_jump", f"index up {r.stress_index - r.prev:.0f} points to {r.stress_index:.0f}"))
        if r.band in ("High", "Severe") and r.prev_band not in ("High", "Severe"):
            out.append((r.district, r.month, "band_up", f"moved into {r.band}"))
        for c in WEIGHTS:
            s = getattr(r, f"score_{c}")
            if pd.notna(s) and s >= 90:
                out.append((r.district, r.month, "component_extreme", f"{LABELS[c]} at {s:.0f}/100"))
    for col, label in RAW.items():
        if col not in panel:
            continue
        v = pd.to_numeric(panel[col], errors="coerce")
        med = v.groupby(panel.district).transform("median")
        mad = (v - med).abs().groupby(panel.district).transform("median") * 1.4826
        z = (v - med) / mad.where(mad > 0)
        for i in z[z.abs() >= 3].index:
            out.append((panel.district[i], panel.month[i], "raw_outlier",
                        f"{label} {'high' if z[i] > 0 else 'low'} ({z[i]:+.1f} robust z)"))
    df = pd.DataFrame(out, columns=["district", "month", "flag", "detail"]).drop_duplicates()
    df = df[~((df.flag == "raw_outlier") & df.detail.str.startswith(("pawn", "gold loan", "instant")) &
              df.duplicated(["month", "detail"]))]  # state-level signals: one row is enough
    df.sort_values(["month", "district"]).to_csv(PROCESSED / "anomaly_flags.csv", index=False)
    return df


if __name__ == "__main__":
    f = flags()
    print(f"{len(f)} flags; latest month:")
    print(f[f.month == f.month.max()].to_string(index=False))
