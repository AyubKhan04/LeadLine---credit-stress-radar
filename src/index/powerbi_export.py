"""Export tidy CSVs for Power BI (phase 7). Run: python -m src.index.powerbi_export

Writes data/powerbi/:
  fact_stress.csv       district x month: index, band, reason, sub-scores, points
  fact_signals.csv      district x month: the raw inputs (rain, gold, rates, searches, auctions)
  dim_district.csv      district, lat, lon (for the map visual)
  dim_component.csv     component, label, weight
  dim_date.csv          month, year, month number, month name, quarter
See docs/powerbi_guide.md for how to build the report.
"""
import pandas as pd

from src.config import ROOT, DISTRICTS, PROCESSED
from src.index.stress_index import WEIGHTS, LABELS

OUT = ROOT / "data" / "powerbi"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    idx = pd.read_csv(PROCESSED / "stress_index_monthly.csv")
    idx.to_csv(OUT / "fact_stress.csv", index=False)
    pd.read_csv(PROCESSED / "panel_monthly.csv").to_csv(OUT / "fact_signals.csv", index=False)
    pd.DataFrame([dict(district=d, latitude=a, longitude=b, state="Tamil Nadu", country="India")
                  for d, (a, b) in DISTRICTS.items()]).to_csv(OUT / "dim_district.csv", index=False)
    pd.DataFrame([dict(component=c, label=LABELS[c], weight=w) for c, w in WEIGHTS.items()]) \
        .to_csv(OUT / "dim_component.csv", index=False)
    m = pd.period_range(idx.month.min(), idx.month.max(), freq="M")
    pd.DataFrame(dict(month=m.astype(str), date=m.to_timestamp().date, year=m.year,
                      month_num=m.month, month_name=m.strftime("%b"), quarter="Q" + m.quarter.astype(str))) \
        .to_csv(OUT / "dim_date.csv", index=False)
    print("Power BI files:", sorted(p.name for p in OUT.glob("*.csv")))


if __name__ == "__main__":
    main()
