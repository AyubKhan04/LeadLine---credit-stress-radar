"""Phase 4 analysis: seasonality, lead-lag, Granger causality, known stress periods.

There is no official monthly district credit-stress series to test against, so
the target here is the strongest demand-side signal we have for distress
borrowing: Google searches in Tamil for pawning jewellery ("நகை அடகு", "நகை கடன்",
averaged as `pawn_search`). The question each test asks: does this driver move
*before* pawn searches do?

Writes docs/analysis.md, docs/img/*.png and data/processed/analysis_*.csv.
Run: python -m src.analysis.explore
"""
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL
from statsmodels.tsa.stattools import adfuller, grangercausalitytests

from src.config import ROOT, PROCESSED
from src.analysis.panel import build_panel

warnings.filterwarnings("ignore")
DOCS = ROOT / "docs"
IMG = DOCS / "img"
IMG.mkdir(parents=True, exist_ok=True)

# Episodes we'd expect a credit stress radar to light up. Dates from public reporting.
EPISODES = [
    ("COVID lockdown", "2020-04", "2020-06", "all", "income stop, gold loan rush"),
    ("Delta wave", "2021-04", "2021-06", "all", "second lockdown in TN"),
    ("RBI tightening", "2022-05", "2023-02", "all", "repo 4.0% to 6.5%"),
    ("Cyclone Michaung floods", "2023-12", "2024-01", "Chennai", "Chennai flooding"),
    ("Cyclone Fengal floods", "2024-12", "2025-01", "Villupuram", "Villupuram flooding"),
]

DRIVERS = {
    "rain_deficit": "Rainfall deficit (4-district mean, % below normal)",
    "gold_inr_yoy_pct": "Gold price in INR, % change on a year ago",
    "repo_rate": "RBI repo rate",
    "trends_instant_loan": "Searches: instant loan",
    "trends_loan_app": "Searches: loan app",
    "app_complaint_share": "Loan-app review complaint share",
}
TARGET = "pawn_search"


def state_series(panel):
    """District panel -> one state-level monthly frame."""
    s = panel.groupby("month").agg(
        rain_anomaly_pct=("rain_anomaly_pct", "mean"),
        gold_inr_yoy_pct=("gold_inr_yoy_pct", "first"),
        repo_rate=("repo_rate", "first"),
        trends_gold_loan=("trends_gold_loan", "first"),
        trends_nagai_adagu=("trends_nagai_adagu", "first"),
        trends_nagai_kadan=("trends_nagai_kadan", "first"),
        trends_instant_loan=("trends_instant_loan", "first"),
        trends_loan_app=("trends_loan_app", "first"),
        app_complaint_share=("app_complaint_share", "first"),
    )
    s.index = pd.PeriodIndex(s.index, freq="M")
    s["rain_deficit"] = -s.rain_anomaly_pct.clip(upper=100)  # positive = drier than normal
    s[TARGET] = s[["trends_nagai_adagu", "trends_nagai_kadan"]].mean(axis=1)
    return s


def seasonality(s):
    rows, fig, axes = [], *plt.subplots(2, 1, figsize=(9, 6), sharex=False)
    for col in [TARGET, "trends_gold_loan", "trends_instant_loan"]:
        x = s[col].dropna()
        res = STL(x.values, period=12, robust=True).fit()
        strength = max(0.0, 1 - np.var(res.resid) / np.var(res.resid + res.seasonal))
        prof = x.groupby(x.index.month).mean()
        prof = (prof / prof.mean() - 1) * 100
        rows.append(dict(series=col, seasonal_strength=round(strength, 2),
                         peak_month=int(prof.idxmax()), trough_month=int(prof.idxmin()),
                         peak_vs_avg_pct=round(prof.max(), 1)))
        axes[0].plot(range(1, 13), prof.values, marker="o", label=col)
        if col == TARGET:
            axes[1].plot(x.index.to_timestamp(), x.values, color="#888", lw=1, label="raw")
            axes[1].plot(x.index.to_timestamp(), res.trend, color="#c0392b", lw=2, label="trend")
    axes[0].axhline(0, color="#999", lw=0.8)
    axes[0].set(title="Month-of-year profile (% vs yearly average)", xticks=range(1, 13))
    axes[0].legend(fontsize=8)
    axes[1].set(title="Tamil pawn searches: raw and trend")
    axes[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(IMG / "seasonality.png", dpi=110)
    plt.close(fig)
    return pd.DataFrame(rows)


def stationary(x):
    """Deseasonalise (12-month difference) if not stationary; return series and how."""
    x = x.dropna()
    if len(x) < 24:
        return x, "too short"
    if adfuller(x, autolag="AIC")[1] < 0.05:
        return x, "level"
    d = x.diff(12).dropna()
    if len(d) >= 24 and adfuller(d, autolag="AIC")[1] < 0.05:
        return d, "12-month change"
    return x.diff().dropna(), "1-month change"


def lead_lag(s, max_lag=6):
    target, how_t = stationary(s[TARGET])
    out, gr = [], []
    for col in DRIVERS:
        x, how = stationary(s[col])
        df = pd.concat([target.rename("y"), x.rename("x")], axis=1).dropna()
        if len(df) < 30:
            out.append(dict(driver=col, n=len(df), note="too few overlapping months"))
            continue
        cc = {k: df.y.corr(df.x.shift(k)) for k in range(-max_lag, max_lag + 1)}
        best = max(cc, key=lambda k: abs(cc[k]) if not np.isnan(cc[k]) else -1)
        try:
            g = grangercausalitytests(df[["y", "x"]].values, maxlag=max_lag)
            pv = {lag: r[0]["ssr_ftest"][1] for lag, r in g.items()}
            best_g = min(pv, key=pv.get)
        except Exception as e:
            pv, best_g = {}, None
        out.append(dict(driver=col, transform=how, n=len(df), best_lag=best,
                        corr_at_best=round(cc[best], 2), corr_lag0=round(cc[0], 2),
                        granger_best_lag=best_g,
                        granger_p=round(pv[best_g], 3) if best_g else None))
        gr.append((col, cc))
    fig, ax = plt.subplots(figsize=(9, 4))
    for col, cc in gr:
        ax.plot(list(cc), list(cc.values()), marker=".", label=col)
    ax.axhline(0, color="#999", lw=0.8)
    ax.axvline(0, color="#999", lw=0.8)
    ax.set(title=f"Cross-correlation with pawn searches ({how_t}); positive lag = driver leads",
           xlabel="lag (months)", ylabel="correlation")
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(IMG / "lead_lag.png", dpi=110)
    plt.close(fig)
    return pd.DataFrame(out)


def episodes(panel, s):
    """Mean z-score of each signal inside each episode vs the whole history."""
    cols = [TARGET, "trends_gold_loan", "trends_instant_loan", "rain_deficit", "gold_inr_yoy_pct"]
    z = (s[cols] - s[cols].mean()) / s[cols].std()
    # district rainfall for district-specific episodes
    p = panel.copy()
    p["rain_deficit"] = -p.rain_anomaly_pct.clip(upper=100)
    p["z_rain"] = p.groupby("district").rain_deficit.transform(lambda v: (v - v.mean()) / v.std())
    rows = []
    for name, a, b, where, why in EPISODES:
        win = z.loc[pd.Period(a, "M"):pd.Period(b, "M")]
        r = dict(episode=name, months=f"{a}..{b}", where=where, context=why)
        r.update({f"z_{c}": round(win[c].mean(), 2) for c in cols})
        if where != "all":
            dz = p[(p.district == where) & (p.month >= a) & (p.month <= b)].z_rain.mean()
            r["z_rain_deficit"] = round(dz, 2)  # district rain, not state mean
        rows.append(r)
    return pd.DataFrame(rows)


def md_table(df):
    df = df.fillna("")
    head = "| " + " | ".join(df.columns) + " |\n|" + "---|" * len(df.columns) + "\n"
    return head + "\n".join("| " + " | ".join(str(v) for v in r) + " |" for r in df.values)


def main():
    panel = build_panel()
    s = state_series(panel)
    sea, ll, ep = seasonality(s), lead_lag(s), episodes(panel, s)
    sea.to_csv(PROCESSED / "analysis_seasonality.csv", index=False)
    ll.to_csv(PROCESSED / "analysis_lead_lag.csv", index=False)
    ep.to_csv(PROCESSED / "analysis_episodes.csv", index=False)

    sig = ll[ll.granger_p.notna() & (ll.granger_p < 0.05)] if "granger_p" in ll else ll.iloc[0:0]
    md = f"""# Phase 4: what the signals say

Generated by `python -m src.analysis.explore` from `data/processed/panel_monthly.csv`
({s.index.min()} to {s.index.max()}). Numbers refresh when the script reruns.

**Target.** There is no public monthly series of household credit stress by district,
so the yardstick is Google searches in Tamil for pawning jewellery (`நகை அடகு`,
`நகை கடன்`), called *pawn searches* below. People search for this when they need cash
against gold, so it is the closest open proxy for distress borrowing in Tamil Nadu.
Gold auction counts would be the better target, but the lender only posts about
7 months of notices, which is too short for these tests (see README).

## 1. Seasonality

![seasonality](img/seasonality.png)

{md_table(sea)}

*Seasonal strength* runs 0 to 1 (STL decomposition); above about 0.4 the calendar
explains a lot of the movement, so the index must compare each month with the same
month in other years, not with last month.

## 2. Lead-lag and Granger causality

![lead-lag](img/lead_lag.png)

{md_table(ll)}

How to read it: `best_lag` > 0 means the driver moves that many months **before**
pawn searches. `granger_p` < 0.05 means past values of the driver improve a forecast
of pawn searches beyond what pawn searches' own past gives. Series are made
stationary first (`transform`). Granger causality is about forecasting, not proof
of cause. The lowest p-value across lags 1-6 is shown, which flatters
results a little (six tries), so treat p between 0.01 and 0.05 as a hint.

Drivers with Granger p < 0.05: {", ".join(sig.driver) if len(sig) else "none at the 5% level"}.

## 3. Known stress periods

Mean z-score inside each window (0 = normal, +1 = one standard deviation above
normal). For district episodes, `z_rain_deficit` uses that district's own rainfall.

{md_table(ep)}

Reading the episodes: pawn searches **fell** during the COVID lockdowns, when
branches were shut and Trends' relative scale was swamped by health searches. So
search signals can miss stress when access itself stops. The flood episodes show the
district's rainfall as wetter than normal (negative deficit), so the rain signal must
treat extreme excess rain as stress too, not only drought.

## What this means for the index (phase 5)

- Score rainfall on both tails: deficit and flood-level excess.
- Use year-on-year or same-month comparisons for seasonal series.
- Weight drivers by how well they lead, but keep the weights simple and visible,
  because the history is short and the target is a proxy.
- Treat the auction counts as a confirming signal once a year of history builds up.
"""
    (DOCS / "analysis.md").write_text(md)
    print(sea.to_string(), "\n\n", ll.to_string(), "\n\n", ep.to_string())


if __name__ == "__main__":
    main()
