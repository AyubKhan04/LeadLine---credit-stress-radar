"""Check the index against real loan defaults: Tamil Nadu SLBC district NPA figures.

The State Level Bankers' Committee (convenor: Indian Bank) publishes quarterly agenda
books with district-wise lending and NPA (bad loan) ratios:
https://www.indianbank.in/slbc/  (PDFs, one per quarter).

Type the figures into data/external/slbc_tn_npa.csv, one row per district and quarter:
    quarter,district,npa_pct,source
    2024Q3,Chennai,3.1,SLBC agenda Dec24 (Q3) p.57

Then run  python -m src.analysis.validate_npa  which writes docs/validation.md.
Question asked: does a high index this quarter come before a rise in NPAs 1-2 quarters later?
With only a few quarters and 4 districts the answer will be rough, and the report says so.
"""
import numpy as np
import pandas as pd

from src.config import PROCESSED, ROOT

NPA = ROOT / "data" / "external" / "slbc_tn_npa.csv"
OUT = ROOT / "docs" / "validation.md"
LAGS = (0, 1, 2)  # quarters the index leads by


def quarterly_index():
    idx = pd.read_csv(PROCESSED / "stress_index_monthly.csv").dropna(subset=["stress_index"])
    idx["quarter"] = pd.PeriodIndex(idx.month, freq="Q").astype(str)
    return idx.groupby(["district", "quarter"]).stress_index.mean().reset_index()


def lead_table(q, npa):
    """Pooled correlation of index (t) with NPA change (t+lag) across district-quarters."""
    npa = npa.sort_values(["district", "quarter"]).copy()
    npa["npa_change"] = npa.groupby("district").npa_pct.diff()
    rows = []
    for lag in LAGS:
        x = q.copy()
        x["quarter"] = (pd.PeriodIndex(x.quarter, freq="Q") + lag).astype(str)
        m = x.merge(npa, on=["district", "quarter"]).dropna(subset=["npa_change"])
        r = m.stress_index.corr(m.npa_change) if len(m) >= 3 else np.nan
        rows.append(dict(index_leads_by_quarters=lag, pairs=len(m), corr=round(r, 2) if pd.notna(r) else None))
    return pd.DataFrame(rows)


def _md(t):
    rows = [list(t.columns)] + t.astype(object).where(t.notna(), "").values.tolist()
    return "\n".join("| " + " | ".join(map(str, r)) + " |" + ("\n|" + "---|" * len(t.columns) if i == 0 else "")
                     for i, r in enumerate(rows))


def run():
    npa = pd.read_csv(NPA) if NPA.exists() else pd.DataFrame(columns=["quarter", "district", "npa_pct"])
    npa = npa.dropna(subset=["npa_pct"])
    lines = ["# Validation against real defaults (SLBC district NPA)", "",
             "Source: Tamil Nadu SLBC quarterly agenda books (https://www.indianbank.in/slbc/), "
             "district-wise NPA %, typed into `data/external/slbc_tn_npa.csv`.", ""]
    if len(npa) < 8:
        lines += ["**Status: not validated yet.** "
                  f"Only {len(npa)} district-quarter NPA figures are entered; at least 8 (2 per district) are needed "
                  "for even a rough check. Until then, the index is checked only against known stress "
                  "episodes (see the README backtest), which is a weaker test.", "",
                  "How to add data: open a quarterly agenda PDF, find the district-wise NPA table, and add one "
                  "row per v1 district (Chennai, Coimbatore, Madurai, Villupuram) to the CSV. Then run "
                  "`python -m src.analysis.validate_npa`."]
    else:
        t = lead_table(quarterly_index(), npa)
        best = t.dropna(subset=["corr"]).sort_values("corr", ascending=False).head(1)
        lines += [f"{len(npa)} district-quarters entered.", "", _md(t), "",
                  "`corr` is the correlation between the index in one quarter and the change in NPA % "
                  "`index_leads_by_quarters` later. Positive means a high index came before rising bad loans.", ""]
        if len(best) and best.iloc[0]["corr"] is not None and best.iloc[0]["corr"] > 0.3:
            b = best.iloc[0]
            lines.append(f"Best lead: {int(b.index_leads_by_quarters)} quarter(s), corr {b['corr']}, on "
                         f"{int(b.pairs)} pairs. With this few pairs it is a hint, not proof.")
        else:
            lines.append("No clear lead: the index does not (yet) line up with later NPA rises. "
                         "Possible reasons: too few quarters, NPAs lag hardship by more than 2 quarters, "
                         "or the index tracks something else.")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return "\n".join(lines)


if __name__ == "__main__":
    print(run())
