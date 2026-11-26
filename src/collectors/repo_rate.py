"""RBI policy repo rate, expanded to a monthly series.

RBI has no simple keyless API, so the change dates are taken from RBI's MPC
press releases and kept here as a small table. Add a row when the MPC changes
the rate. Monthly value = rate in force on the last day of the month.
"""
import pandas as pd
from src.config import START, TODAY, PROCESSED

# (effective date, repo rate %) - source: RBI Monetary Policy Statements / press releases
CHANGES = [
    ("2018-08-01", 6.50),
    ("2019-02-07", 6.25),
    ("2019-04-04", 6.00),
    ("2019-06-06", 5.75),
    ("2019-08-07", 5.40),
    ("2019-10-04", 5.15),
    ("2020-03-27", 4.40),
    ("2020-05-22", 4.00),
    ("2022-05-04", 4.40),
    ("2022-06-08", 4.90),
    ("2022-08-05", 5.40),
    ("2022-09-30", 5.90),
    ("2022-12-07", 6.25),
    ("2023-02-08", 6.50),
    ("2025-02-07", 6.25),
    ("2025-04-09", 6.00),
    ("2025-06-06", 5.50),
    ("2025-12-05", 5.25),
    ("2026-10-07", 5.50),
]


def main():
    ch = pd.DataFrame(CHANGES, columns=["date", "repo_rate"])
    ch["date"] = pd.to_datetime(ch["date"])
    months = pd.period_range(START, TODAY, freq="M")
    month_end = months.to_timestamp(how="end").normalize()
    idx = ch.set_index("date")["repo_rate"]
    rates = [idx[idx.index <= d].iloc[-1] for d in month_end]
    out = pd.DataFrame({"month": months.astype(str), "repo_rate": rates})
    out["repo_rate_change_bps"] = (out["repo_rate"].diff() * 100).round().fillna(0).astype(int)
    out.to_csv(PROCESSED / "repo_rate_monthly.csv", index=False)
    print(f"repo rate: {len(out)} months, latest {out.iloc[-1].to_dict()}")


if __name__ == "__main__":
    main()
