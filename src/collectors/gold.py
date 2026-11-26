"""Monthly gold price in INR per 10 g.

Gold (USD/troy oz, monthly average) comes from the World Bank Commodity Price
Data ("Pink Sheet", CC BY 4.0). USD/INR (monthly average) comes from FRED series
EXINUS (Federal Reserve H.10). INR/10g = USD/oz * INR/USD * 10 / 31.1035.

This is the international benchmark converted to rupees. It excludes import duty
and GST, so Indian retail/IBJA prices run higher; the month-on-month movement is
what the index uses. IBJA publishes daily rates but has no open API and its terms
don't allow bulk reuse, so it isn't scraped.
"""
import io
import pandas as pd
import requests

from src.config import START, RAW, PROCESSED, USER_AGENT

# World Bank moves this file each year; try the newest location first.
PINK_SHEET_URLS = [
    "https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx",
    "https://thedocs.worldbank.org/en/doc/18675f1d1639c7a34d463f59263ba0a2-0050012025/related/CMO-Historical-Data-Monthly.xlsx",
    "https://thedocs.worldbank.org/en/doc/5d903e848db1d1b83e0ec8f744e55570-0350012021/related/CMO-Historical-Data-Monthly.xlsx",
]
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=EXINUS"
GRAMS_PER_TROY_OZ = 31.1035


def get(url):
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=90)
    r.raise_for_status()
    return r.content


def gold_usd():
    last_err = None
    for url in PINK_SHEET_URLS:
        try:
            content = get(url)
            break
        except Exception as e:
            last_err = e
            print(f"[gold] {url} failed: {e}")
    else:
        raise RuntimeError(f"Pink Sheet not reachable: {last_err}")
    (RAW / "worldbank_pinksheet_monthly.xlsx").write_bytes(content)
    sheet = pd.read_excel(io.BytesIO(content), sheet_name="Monthly Prices", header=None)
    hdr = sheet.index[sheet.apply(lambda r: r.astype(str).str.strip().eq("Gold").any(), axis=1)][0]
    col = sheet.columns[sheet.loc[hdr].astype(str).str.strip().eq("Gold")][0]
    data = sheet.loc[hdr + 1:, [sheet.columns[0], col]].dropna()
    data.columns = ["wb_month", "gold_usd_oz"]
    data = data[data["wb_month"].astype(str).str.match(r"^\d{4}M\d{2}$")]
    data["month"] = data["wb_month"].str.replace("M", "-")
    data["gold_usd_oz"] = pd.to_numeric(data["gold_usd_oz"], errors="coerce")
    return data[["month", "gold_usd_oz"]]


def usd_inr():
    fx = pd.read_csv(io.BytesIO(get(FRED_URL)))
    fx.columns = ["date", "usd_inr"]
    fx["usd_inr"] = pd.to_numeric(fx["usd_inr"], errors="coerce")
    fx["month"] = pd.to_datetime(fx["date"]).dt.to_period("M").astype(str)
    fx.to_csv(RAW / "fred_exinus.csv", index=False)
    return fx[["month", "usd_inr"]].dropna()


def main():
    df = gold_usd().merge(usd_inr(), on="month", how="left")
    df = df[df["month"] >= START.strftime("%Y-%m")].copy()
    df["gold_inr_10g"] = (df["gold_usd_oz"] * df["usd_inr"] * 10 / GRAMS_PER_TROY_OZ).round(0)
    df["gold_inr_mom_pct"] = (df["gold_inr_10g"].pct_change(fill_method=None) * 100).round(2)
    df["gold_inr_yoy_pct"] = (df["gold_inr_10g"].pct_change(12, fill_method=None) * 100).round(2)
    df.to_csv(PROCESSED / "gold_monthly.csv", index=False)
    print(f"gold: {len(df)} rows, {df['month'].min()}..{df['month'].max()}, "
          f"FX missing for {df['usd_inr'].isna().sum()} months")


if __name__ == "__main__":
    main()
