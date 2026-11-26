"""Loan-app reviews -> monthly counts of credit-stress complaints.

Source: Apple App Store public customer-review RSS feed (India storefront).
Google Play was the first choice, but play.google.com/robots.txt disallows the
endpoints review scrapers use (/_/ and /store/getreviews), so it is not scraped.

Privacy: reviewer names and ids are dropped on read. Review text is kept only
in data/raw (git-ignored); the committed file holds monthly counts only.
Limit: Apple's feed returns at most the 500 most recent reviews per app, so
history is short for busy apps.
"""
import os
import time
import pandas as pd
import requests
from dotenv import load_dotenv

from src.config import RAW, PROCESSED, USER_AGENT, robots_allows
from src.classify.review_classifier import LABELS, ai_labels, language, rule_labels

load_dotenv()

# Search term -> word that must appear in the matched app name (guards against wrong matches)
APPS = {
    "KreditBee": "kreditbee", "Navi loan": "navi", "Moneyview": "money", "Fibe instant loan": "fibe",
    "mPokket": "mpokket", "CASHe": "cashe", "Kissht": "kissht", "Bajaj Finserv": "bajaj",
    "Muthoot FinCorp ONE": "muthoot", "Manappuram gold loan": "manappuram", "Rupeek gold loan": "rupeek",
    "IIFL Finance loan": "iifl",
}
SEARCH = "https://itunes.apple.com/search"
FEED = "https://itunes.apple.com/in/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"
H = {"User-Agent": USER_AGENT}


def find_app(term, must):
    r = requests.get(SEARCH, params={"term": term, "country": "in", "entity": "software", "limit": 5},
                     headers=H, timeout=30)
    r.raise_for_status()
    for a in r.json().get("results", []):
        if must in a["trackName"].lower().replace(" ", ""):
            return a["trackId"], a["trackName"]
    return None, None


def fetch_reviews(app_id, app_name):
    rows = []
    for page in range(1, 11):
        r = requests.get(FEED.format(page=page, app_id=app_id), headers=H, timeout=30)
        if r.status_code != 200:
            break
        entries = r.json().get("feed", {}).get("entry", [])
        if isinstance(entries, dict):
            entries = [entries]
        entries = [e for e in entries if "im:rating" in e]  # first entry can be app metadata
        if not entries:
            break
        for e in entries:  # author fields deliberately not read
            rows.append({
                "app": app_name,
                "date": e["updated"]["label"][:10],
                "rating": int(e["im:rating"]["label"]),
                "text": f'{e.get("title", {}).get("label", "")}. {e.get("content", {}).get("label", "")}',
            })
        time.sleep(1)
    return rows


def main():
    if not robots_allows(FEED.format(page=1, app_id=1)):
        print("app reviews: robots.txt disallows the feed; skipping")
        return
    rows, missing = [], []
    for term, must in APPS.items():
        try:
            app_id, name = find_app(term, must)
            if not app_id:
                missing.append(term)
                continue
            got = fetch_reviews(app_id, name)
            print(f"  {name}: {len(got)} reviews")
            rows += got
        except Exception as e:
            print(f"  {term}: failed ({e})")
            missing.append(term)
        time.sleep(1)
    if not rows:
        print("app reviews: nothing collected")
        return

    df = pd.DataFrame(rows).drop_duplicates()
    df["lang"] = df["text"].map(language)
    df["labels"] = df["text"].map(rule_labels)
    df["labelled_by"] = df["labels"].map(lambda l: "rules" if l else "")

    # Optional AI pass: only low-star reviews the rules didn't catch
    todo = df[(df["rating"] <= 2) & (df["labels"].str.len() == 0)]
    todo = todo.head(int(os.getenv("LEADLINE_AI_MAX_REVIEWS", "300")))
    ai = ai_labels(todo["text"].tolist())
    if ai is None:
        print("AI classifier skipped (no ANTHROPIC_API_KEY)")
    else:
        for idx, labels in zip(todo.index, ai):
            if labels:
                df.at[idx, "labels"], df.at[idx, "labelled_by"] = labels, "ai"
        print(f"AI classifier labelled {sum(bool(l) for l in ai)} of {len(ai)} reviews")

    df.to_json(RAW / "app_reviews_labelled.jsonl", orient="records", lines=True, force_ascii=False)

    df["month"] = pd.to_datetime(df["date"]).dt.to_period("M").astype(str)
    df["stress"] = df["labels"].str.len() > 0
    for lab in LABELS:
        df[lab] = df["labels"].map(lambda l, lab=lab: lab in l)
    agg = {"reviews": ("rating", "size"), "low_star": ("rating", lambda s: (s <= 2).sum()),
           "stress_complaints": ("stress", "sum"),
           "tamil_reviews": ("lang", lambda s: (s == "ta").sum()),
           "ai_labelled": ("labelled_by", lambda s: (s == "ai").sum())}
    agg.update({lab: (lab, "sum") for lab in LABELS})
    monthly = df.groupby(["month", "app"]).agg(**agg).reset_index()
    monthly.to_csv(PROCESSED / "app_reviews_monthly_by_app.csv", index=False)
    total = monthly.drop(columns="app").groupby("month").sum().reset_index()
    total["stress_share"] = (total["stress_complaints"] / total["reviews"]).round(3)
    total.to_csv(PROCESSED / "app_reviews_monthly.csv", index=False)
    print(f"app reviews: {len(df)} reviews from {df['app'].nunique()} apps, "
          f"{df['month'].min()}..{df['month'].max()}; not found: {missing}")


if __name__ == "__main__":
    main()
