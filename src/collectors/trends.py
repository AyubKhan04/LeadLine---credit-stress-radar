"""Google Trends search interest for credit-stress terms in Tamil Nadu.

Uses pytrends (unofficial). robots.txt on trends.google.com only disallows the
/explore? web page, not the /trends/api endpoints pytrends calls; we still keep
volume tiny (one request per term) with pauses between calls.

Outputs
- trends_tn_monthly.csv: monthly 0-100 interest per term for Tamil Nadu (IN-TN).
  Each term is fetched on its own, so values compare months within a term, not
  terms with each other.
City level: Google gives no city time series for India, and the city breakdown
inside IN-TN came back empty for every term and year in testing, so it was dropped.
"""
import time
import pandas as pd
from pytrends.request import TrendReq

from src.config import START, TODAY, RAW, PROCESSED

TERMS = ["gold loan", "instant loan", "loan app", "நகை அடகு", "நகை கடன்"]
GEO = "IN-TN"
PAUSE = 8  # seconds between calls, to stay polite and avoid 429s


def client():
    # no retries= here: pytrends' retry option breaks on urllib3 2.x, so we retry ourselves
    return TrendReq(hl="en-IN", tz=-330, timeout=(10, 30))


def with_retry(fn, tries=3):
    for attempt in range(tries):
        try:
            return fn()
        except Exception as e:
            if attempt == tries - 1:
                raise
            wait = 60 * (attempt + 1) if "429" in str(e) else 10
            print(f"[trends] retry in {wait}s after: {str(e)[:120]}")
            time.sleep(wait)


def main():
    py = client()
    frames, failed = [], []
    timeframe = f"{START.isoformat()} {TODAY.isoformat()}"
    for term in TERMS:
        try:
            def ts_call():
                py.build_payload([term], timeframe=timeframe, geo=GEO)
                return py.interest_over_time()
            ts = with_retry(ts_call)
            if ts.empty:
                failed.append((term, "no data"))
            else:
                ts = ts.reset_index().rename(columns={term: "interest"})
                ts["term"] = term
                frames.append(ts[["date", "term", "interest", "isPartial"]])
        except Exception as e:
            failed.append((term, f"timeseries: {e}"))
        time.sleep(PAUSE)


    if frames:
        ts = pd.concat(frames)
        ts.to_csv(RAW / "trends_tn_raw.csv", index=False)
        ts["month"] = pd.to_datetime(ts["date"]).dt.to_period("M").astype(str)
        out = (ts.groupby(["term", "month"], as_index=False)
                 .agg(interest=("interest", "mean"), partial=("isPartial", "max")))
        out["interest"] = out["interest"].round(1)
        out.to_csv(PROCESSED / "trends_tn_monthly.csv", index=False)
        print(f"trends: {out['term'].nunique()} terms, {out['month'].min()}..{out['month'].max()}")
    fail_file = PROCESSED / "trends_failures.csv"
    fail_file.unlink(missing_ok=True)
    if failed:
        pd.DataFrame(failed, columns=["term", "error"]).to_csv(fail_file, index=False)
        print(f"trends: {len(failed)} calls failed (see trends_failures.csv)")


if __name__ == "__main__":
    main()
