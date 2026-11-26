"""Join every processed signal into one district x month panel.

Grain: district (the 4 v1 districts) x month. State or national signals are
repeated for each district. Output: data/processed/panel_monthly.csv
"""
import pandas as pd

from src.config import PROCESSED, DISTRICTS

TREND_COLS = {"gold loan": "trends_gold_loan", "நகை அடகு": "trends_nagai_adagu",
              "நகை கடன்": "trends_nagai_kadan", "instant loan": "trends_instant_loan",
              "loan app": "trends_loan_app"}


def _read(name):
    p = PROCESSED / name
    return pd.read_csv(p) if p.exists() else None


def build_panel(save=True):
    rain = _read("rainfall_monthly.csv")[["district", "month", "rain_mm", "rain_anomaly_pct"]]
    gold = _read("gold_monthly.csv")[["month", "gold_inr_10g", "gold_inr_mom_pct", "gold_inr_yoy_pct"]]
    repo = _read("repo_rate_monthly.csv")
    tr = _read("trends_tn_monthly.csv")
    tr = tr[tr.term.isin(TREND_COLS)].assign(term=lambda d: d.term.map(TREND_COLS))
    tr = tr.pivot_table(index="month", columns="term", values="interest").reset_index()

    # loan-app complaint share: Play dataset (2019-2022) then Apple feed (2026-); gaps stay empty
    rev = []
    for f in ("play_reviews_dataset_monthly.csv", "app_reviews_monthly.csv"):
        d = _read(f)
        if d is not None and len(d):
            d = d[d.reviews >= 20] if f.startswith("play") else d[d.reviews >= 5]
            rev.append(d[["month", "stress_share"]])
    rev = (pd.concat(rev).groupby("month").stress_share.mean().rename("app_complaint_share").reset_index()
           if rev else pd.DataFrame(columns=["month", "app_complaint_share"]))

    months = pd.period_range(rain.month.min(), rain.month.max(), freq="M").astype(str)
    base = pd.MultiIndex.from_product([list(DISTRICTS), months], names=["district", "month"]).to_frame(index=False)
    panel = (base.merge(rain, on=["district", "month"], how="left")
             .merge(gold, on="month", how="left").merge(repo, on="month", how="left")
             .merge(tr, on="month", how="left").merge(rev, on="month", how="left"))

    auc = _read("gold_auctions_monthly.csv")
    if auc is not None and len(auc):
        panel = panel.merge(auc[["district", "month", "auction_accounts", "auction_branches"]],
                            on=["district", "month"], how="left")
    else:
        panel["auction_accounts"] = pd.NA
        panel["auction_branches"] = pd.NA
    panel = panel.sort_values(["district", "month"]).reset_index(drop=True)
    if save:
        panel.to_csv(PROCESSED / "panel_monthly.csv", index=False)
    return panel


if __name__ == "__main__":
    p = build_panel()
    print(p.shape, p.month.min(), p.month.max())
    print(p.notna().mean().round(2).to_string())
