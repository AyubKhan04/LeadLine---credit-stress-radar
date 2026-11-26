"""Monthly rainfall per district from Open-Meteo's historical archive (ERA5 reanalysis).

Why not IMD? IMD district rainfall on data.gov.in needs an API key and its public
district series stops years ago. Open-Meteo is free, keyless, CC BY 4.0, and daily
back to 1940. It is a modelled grid value at the district HQ point, not a rain-gauge
district average, so treat it as a proxy.
"""
import time
import pandas as pd
import requests

from src.config import DISTRICTS, START, TODAY, RAW, PROCESSED, USER_AGENT, robots_allows

URL = "https://archive-api.open-meteo.com/v1/archive"


def fetch_district(name, lat, lon):
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": START.isoformat(), "end_date": TODAY.isoformat(),
        "daily": "precipitation_sum", "timezone": "Asia/Kolkata",
    }
    r = requests.get(URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=60)
    r.raise_for_status()
    d = r.json()["daily"]
    df = pd.DataFrame({"date": d["time"], "rain_mm": d["precipitation_sum"]})
    df["district"] = name
    return df


def main():
    robots_allows(URL)
    daily = pd.concat([fetch_district(n, *ll) for n, ll in DISTRICTS.items() if not time.sleep(1)])
    daily.to_csv(RAW / "rainfall_daily_openmeteo.csv", index=False)

    daily["date"] = pd.to_datetime(daily["date"])
    daily["month"] = daily["date"].dt.to_period("M").astype(str)
    m = (daily.groupby(["district", "month"])
              .agg(rain_mm=("rain_mm", "sum"), days_with_data=("rain_mm", "count"),
                   days_in_month=("date", lambda s: s.iloc[0].days_in_month))
              .reset_index())
    m["complete"] = m["days_with_data"] == m["days_in_month"]
    # anomaly vs this series' own calendar-month mean (complete months only)
    m["cal_month"] = m["month"].str[-2:]
    base = m[m["complete"]].groupby(["district", "cal_month"])["rain_mm"].mean().rename("normal_mm")
    m = m.join(base, on=["district", "cal_month"])
    m["rain_anomaly_pct"] = ((m["rain_mm"] - m["normal_mm"]) / m["normal_mm"].where(m["normal_mm"] > 1) * 100).round(1)
    m["rain_mm"] = m["rain_mm"].round(1)
    m["normal_mm"] = m["normal_mm"].round(1)
    out = m[["district", "month", "rain_mm", "normal_mm", "rain_anomaly_pct", "days_with_data", "complete"]]
    out.to_csv(PROCESSED / "rainfall_monthly.csv", index=False)
    print(f"rainfall: {len(out)} rows, {out['month'].min()}..{out['month'].max()}")


if __name__ == "__main__":
    main()
