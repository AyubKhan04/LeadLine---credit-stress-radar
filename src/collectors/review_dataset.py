"""Import a published Play Store review dataset and classify it like the live feed.

Default dataset: "SLICE PAY App Reviews" by PavanKalyan on Kaggle
(kaggle.com/datasets/pavan9065/slice-pay-app-reviews), CC0 public domain.
About 154k Google Play reviews of the slice credit/BNPL app, July 2015 to
2 Aug 2022. Columns: reviewId, userName, content, score, thumbsUpCount, at, replyContent.

How to get the file (Kaggle needs a login to download):
- put slicepay_reviews.csv in data/raw/, or
- set KAGGLE_USERNAME and KAGGLE_KEY and this script downloads it.

Privacy: only content, score and at are read; userName and reviewId are never loaded.
"""
import os
import zipfile
import pandas as pd
import requests

from src.config import RAW, PROCESSED, START
from src.classify.review_classifier import LABELS, ai_labels, language, rule_labels

FILE = RAW / "slicepay_reviews.csv"
KAGGLE_URL = "https://www.kaggle.com/api/v1/datasets/download/pavan9065/slice-pay-app-reviews"


def ensure_file():
    if FILE.exists():
        return True
    user, key = os.getenv("KAGGLE_USERNAME"), os.getenv("KAGGLE_KEY")
    if not (user and key):
        print("review dataset: data/raw/slicepay_reviews.csv not found and no Kaggle credentials; skipping")
        return False
    r = requests.get(KAGGLE_URL, auth=(user, key), timeout=300)
    r.raise_for_status()
    zpath = RAW / "slicepay.zip"
    zpath.write_bytes(r.content)
    with zipfile.ZipFile(zpath) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        FILE.write_bytes(z.read(name))
    zpath.unlink()
    return True


def main():
    if not ensure_file():
        return
    df = pd.read_csv(FILE, usecols=["content", "score", "at"]).dropna(subset=["content", "at"])
    df["at"] = pd.to_datetime(df["at"], errors="coerce")
    df = df[df["at"] >= pd.Timestamp(START)]
    df["rating"] = df["score"].astype(int)
    df["lang"] = df["content"].map(language)
    df["labels"] = df["content"].map(rule_labels)
    df["labelled_by"] = df["labels"].map(lambda l: "rules" if l else "")

    todo = df[(df["rating"] <= 2) & (df["labels"].str.len() == 0)]
    todo = todo.sample(min(len(todo), int(os.getenv("LEADLINE_AI_MAX_REVIEWS", "300"))), random_state=0)
    ai = ai_labels(todo["content"].tolist())
    if ai is None:
        print("AI classifier skipped (no ANTHROPIC_API_KEY)")
    else:
        for idx, labels in zip(todo.index, ai):
            if labels:
                df.at[idx, "labels"], df.at[idx, "labelled_by"] = labels, "ai"

    df["month"] = df["at"].dt.to_period("M").astype(str)
    df["stress"] = df["labels"].str.len() > 0
    for lab in LABELS:
        df[lab] = df["labels"].map(lambda l, lab=lab: lab in l)
    agg = {"reviews": ("rating", "size"), "low_star": ("rating", lambda s: (s <= 2).sum()),
           "stress_complaints": ("stress", "sum"),
           "tamil_reviews": ("lang", lambda s: (s == "ta").sum()),
           "ai_labelled": ("labelled_by", lambda s: (s == "ai").sum())}
    agg.update({lab: (lab, "sum") for lab in LABELS})
    m = df.groupby("month").agg(**agg).reset_index()
    m["stress_share"] = (m["stress_complaints"] / m["reviews"]).round(4)
    m.insert(1, "source", "slice (Google Play, Kaggle CC0)")
    m.to_csv(PROCESSED / "play_reviews_dataset_monthly.csv", index=False)
    print(f"review dataset: {len(df)} reviews, {m['month'].min()}..{m['month'].max()}, "
          f"{int(df['stress'].sum())} stress complaints")


if __name__ == "__main__":
    main()
