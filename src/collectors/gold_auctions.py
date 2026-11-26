"""Gold loan auction notices: Manappuram Finance, Tamil Nadu (phase 3).

Source: https://www.manappuram.com/auction-publications (filter: Tamil Nadu).
Manappuram posts the newspaper page that carries each gold auction notice as a
PDF (Dinamani in Tamil, The New Indian Express in English, one per edition city).
The notice lists the loan accounts whose pledged gold will be auctioned, grouped
by branch. robots.txt allows these paths and the site's terms don't forbid reuse.

Steps
1. List every Tamil Nadu notice (title, edition district, language, PDF link).
2. Build a branch -> district table from the public branch network page
   (committed as manappuram_tn_branches.csv: business addresses only).
3. Download each PDF to data/raw/ (git-ignored), read the text with pdfplumber;
   the PDFs are scanned pages, so fall back to Tesseract OCR on the embedded image.
4. Cut out the Manappuram notice, find branch names, and count the distinct loan
   numbers listed under each branch. The same notice runs in several papers, so
   loan numbers are de-duplicated within a month.
5. Optional: if rules find no branch in a notice and ANTHROPIC_API_KEY is set,
   ask Claude Haiku to split the text into branch -> count (counts only).

Output: gold_auctions_monthly.csv (district x month), plus a branch-level file.
Only counts are written; loan numbers, and any names that OCR picks up, stay in
memory or in git-ignored data/raw/.
"""
import collections
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

from src.config import RAW, PROCESSED, USER_AGENT, DISTRICTS, robots_allows

BASE = "https://www.manappuram.com"
LIST_URL = BASE + "/auction-publications"
BRANCH_URL = BASE + "/branch-network"
TN_STATE_ID = "1032"
RAW_DIR = RAW / "manappuram_auctions"
DELAY = 1.5  # seconds between requests: be gentle

TN_DISTRICTS = [
    "Ariyalur", "Chengalpattu", "Chennai", "Coimbatore", "Cuddalore", "Dharmapuri",
    "Dindigul", "Erode", "Kallakurichi", "Kancheepuram", "Kanyakumari", "Karur",
    "Krishnagiri", "Madurai", "Mayiladuthurai", "Nagapattinam", "Namakkal", "Nilgiris",
    "Perambalur", "Pudukkottai", "Ramanathapuram", "Ranipet", "Salem", "Sivaganga",
    "Tenkasi", "Thanjavur", "Theni", "Thoothukudi", "Tiruchirappalli", "Tirunelveli",
    "Tirupathur", "Tiruppur", "Tiruvallur", "Tiruvannamalai", "Tiruvarur", "Vellore",
    "Villupuram", "Virudhunagar",
]
# spellings the site or the papers use -> canonical district
DISTRICT_ALIASES = {
    "kanchipuram": "Kancheepuram", "thiruvallur": "Tiruvallur", "thiruvannamalai": "Tiruvannamalai",
    "tiruvanamalai": "Tiruvannamalai", "thiruvarur": "Tiruvarur", "trichy": "Tiruchirappalli",
    "tiruchy": "Tiruchirappalli", "tiruchchirappalli": "Tiruchirappalli", "tuticorin": "Thoothukudi",
    "the nilgiris": "Nilgiris", "kanniyakumari": "Kanyakumari", "viluppuram": "Villupuram",
    "villuppuram": "Villupuram", "sivagangai": "Sivaganga", "thirupathur": "Tirupathur",
    "tirupur": "Tiruppur", "thiruppur": "Tiruppur", "nagercoil": "Kanyakumari",
}

session = requests.Session()
session.headers["User-Agent"] = USER_AGENT


def get(url, **kw):
    for attempt in range(3):
        try:
            r = session.get(url, timeout=(15, 90), **kw)
            r.raise_for_status()
            time.sleep(DELAY)
            return r
        except Exception as e:
            if attempt == 2:
                raise
            print(f"[auctions] retry {url[:80]}: {e}")
            time.sleep(5 * (attempt + 1))


def canon_district(name):
    n = re.sub(r"\s+", " ", str(name)).strip().lower()
    if n in DISTRICT_ALIASES:
        return DISTRICT_ALIASES[n]
    for d in TN_DISTRICTS:
        if d.lower() == n:
            return d
    return None


# ---------------------------------------------------------------- 1. notice list
def list_notices():
    rows, page = [], 0
    while True:
        url = f"{LIST_URL}?field_state_target_id={TN_STATE_ID}&page={page}"
        soup = BeautifulSoup(get(url).text, "html.parser")
        trs = soup.select("table tbody tr")
        got = 0
        for tr in trs:
            tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            a = tr.find("a", href=re.compile(r"\.pdf", re.I))
            if not a or len(tds) < 4:
                continue
            title, district, language, state = tds[:4]
            m = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", title)
            pub = None
            if m:
                d, mo, y = map(int, m.groups())
                y = y + 2000 if y < 100 else y
                try:
                    pub = datetime(y, mo, d).date()
                except ValueError:
                    pass
            rows.append(dict(title=title, edition_district=district, language=language,
                             state=state, pub_date=pub, url=urljoin(BASE, a["href"])))
            got += 1
        if not got:
            break
        page += 1
    df = pd.DataFrame(rows).drop_duplicates("url")
    print(f"notices listed: {len(df)} across {page} pages, "
          f"{df.pub_date.min()}..{df.pub_date.max()}" if len(df) else "notices listed: 0")
    return df


# ------------------------------------------------------- 2. branch -> district
def parse_branch_rows(html):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for li in soup.select("li"):
        b = li.select_one(".views-field-nothing .field-content")
        addr = li.select_one(".views-field-field-branch-address .field-content")
        if not b or not addr:
            continue
        parts = [p.strip() for p in b.get_text("\n").split("\n") if p.strip()]
        name = parts[0] if parts else ""
        code = next((p for p in parts[1:] if p.isdigit()), "")
        out.append(dict(branch=name, branch_code=code, address=addr.get_text(" ", strip=True)))
    return out


def branch_table():
    cache = PROCESSED / "manappuram_tn_branches.csv"
    if cache.exists() and (time.time() - cache.stat().st_mtime) < 30 * 86400:
        return pd.read_csv(cache, dtype=str)
    if not robots_allows(BRANCH_URL):
        raise RuntimeError("branch-network disallowed by robots.txt")
    first = get(f"{BRANCH_URL}?field_state_and_district_target_id={TN_STATE_ID}&field_district_target_id=All")
    soup = BeautifulSoup(first.text, "html.parser")
    sel = soup.find("select", attrs={"name": "field_district_target_id"})
    ids = {}
    for o in sel.find_all("option") if sel else []:
        d = canon_district(o.get_text())
        if d:
            ids[d] = o.get("value")
    rows = []
    for d, did in sorted(ids.items()):
        r = get(f"{BRANCH_URL}?field_state_and_district_target_id={TN_STATE_ID}&field_district_target_id={did}")
        for row in parse_branch_rows(r.text):
            rows.append(dict(row, district=d))
    seen = {r["branch_code"] or r["branch"] for r in rows}
    # branches not returned under any district: try "<Name> Dt." in the address
    for row in parse_branch_rows(first.text):
        if (row["branch_code"] or row["branch"]) in seen:
            continue
        m = re.search(r"([A-Za-z ]+?)\s*(?:Dt|Dist|District)\b", row["address"])
        rows.append(dict(row, district=canon_district(m.group(1)) if m else None))
    df = pd.DataFrame(rows).drop_duplicates(["branch", "branch_code"])
    df.to_csv(cache, index=False)
    print(f"branches: {len(df)} in TN, {df.district.notna().sum()} mapped to {df.district.nunique()} districts")
    return df.astype(str)


# --------------------------------------------------------------- 3. PDF -> text
def download(url):
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / re.sub(r"[^A-Za-z0-9._-]+", "_", url.rsplit("/", 2)[-2] + "_" + url.rsplit("/", 1)[-1])
    if not path.exists():
        path.write_bytes(get(url).content)
    return path


def ocr_pdf(path):
    """OCR the largest embedded image of each page (native resolution)."""
    if not shutil.which("tesseract"):
        return ""
    texts = []
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdfimages", "-png", str(path), f"{tmp}/img"], check=False, capture_output=True)
        imgs = sorted(Path(tmp).glob("img-*.png"), key=lambda p: p.stat().st_size, reverse=True)
        if not imgs or imgs[0].stat().st_size < 200_000:  # no real scan inside: render the page
            subprocess.run(["pdftoppm", "-r", "400", "-png", str(path), f"{tmp}/pg"], check=False, capture_output=True)
            imgs = sorted(Path(tmp).glob("pg-*.png"))
        for img in imgs[:3]:
            r = subprocess.run(["tesseract", str(img), "-", "--psm", "3", "-l", "eng"],
                               capture_output=True, text=True)
            texts.append(r.stdout)
    return "\n".join(texts)


def pdf_text(path):
    cache = path.with_suffix(".txt")
    if cache.exists():
        return cache.read_text()
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        text = "\n".join((p.extract_text() or "") for p in pdf.pages)
    method = "pdfplumber"
    if "MANAPPURAM" not in text.upper() or len(text) < 1500:
        text, method = ocr_pdf(path), "ocr"
    cache.write_text(text)  # git-ignored
    print(f"  {path.name}: {method}, {len(text)} chars")
    return text


# ------------------------------------------------------------ 4. text -> counts
LOAN_RE = re.compile(r"\b[A-Z]{0,4}\d{8,20}\b")


def notice_section(text):
    """The Manappuram gold auction notice inside a full newspaper page."""
    up = text.upper()
    starts = [m.start() for m in re.finditer(r"MANAPPURAM", up)]
    if not starts:
        return ""
    s = starts[0]
    end = len(text)
    for pat in (r"AUTHORI[SZ]ED OFFICER", r"FOR MANAPPURAM FINANCE"):
        m = re.compile(pat).search(up, s + 200)
        if m:
            end = min(end, m.end() + 50)
    return text[s:end]


def branch_patterns(branches):
    pats = []
    for b in branches.itertuples():
        name = re.sub(r"\s+", " ", str(b.branch)).strip()
        if len(name) < 3:
            continue
        rx = r"\b" + r"[\s\-.]*".join(re.escape(w) for w in name.upper().split()) + r"\b"
        pats.append((re.compile(rx), name, b.branch_code, b.district))
    pats.sort(key=lambda p: -len(p[1]))  # longest name first so "Madurai Anna Nagar" beats "Madurai"
    return pats


def split_by_branch(section, pats):
    """[(branch, code, district, {loan numbers})] by position in the text."""
    up = section.upper()
    hits, taken = [], []
    for rx, name, code, dist in pats:
        for m in rx.finditer(up):
            if any(a <= m.start() < b for a, b in taken):
                continue
            hits.append((m.start(), m.end(), name, code, dist))
            taken.append((m.start(), m.end()))
    hits.sort()
    out = []
    for i, (s, e, name, code, dist) in enumerate(hits):
        nxt = hits[i + 1][0] if i + 1 < len(hits) else len(up)
        loans = set(LOAN_RE.findall(up[e:nxt]))
        if loans:
            out.append((name, code, dist, loans))
    return out


def ai_split(section):
    """Optional Claude Haiku fallback: returns [(branch, count)]; never stores text."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or not section:
        return []
    import anthropic
    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model="claude-haiku-4-5", max_tokens=1500,
        messages=[{"role": "user", "content":
                   "This is OCR text of a Manappuram Finance gold auction notice from a Tamil Nadu "
                   "newspaper. List each branch and how many loan accounts are listed under it. "
                   "Reply with JSON only: [{\"branch\": str, \"accounts\": int}]. Do not include "
                   "any names or loan numbers.\n\n" + section[:60000]}])
    try:
        txt = msg.content[0].text
        return [(d["branch"], int(d["accounts"])) for d in json.loads(txt[txt.find("["): txt.rfind("]") + 1])]
    except Exception as e:
        print(f"  [ai] could not parse reply: {e}")
        return []


def probe(text, pats, label):
    """Print the notice's layout without personal data: words that aren't branch
    names become W, digits become 9."""
    sec = notice_section(text)
    print(f"  [probe] {label}: page {len(text)} chars, notice {len(sec)} chars, "
          f"loan-like tokens {len(LOAN_RE.findall(sec.upper()))}")
    names = {n.upper() for _, n, _, _ in pats}
    sample = sec[300:1500]
    masked = re.sub(r"[A-Za-z][A-Za-z.]*", lambda m: m.group(0) if m.group(0).upper().strip(".") in names else "W", sample)
    print("  [probe] layout: " + re.sub(r"\d", "9", re.sub(r"\s+", " ", masked))[:900])


# ------------------------------------------------------------------------ main
def main():
    if not robots_allows(LIST_URL + f"?field_state_target_id={TN_STATE_ID}&page=0"):
        print("auction list disallowed by robots.txt; skipping")
        return
    notices = list_notices()
    branches = branch_table()
    pats = branch_patterns(branches)
    seen_loans = collections.defaultdict(set)  # month -> loan numbers already counted
    rows, coverage = [], []
    probe_left = 3 if os.environ.get("AUCTION_PROBE") else 0
    for n in notices.sort_values("pub_date").itertuples():
        if n.pub_date is None:
            continue
        month = n.pub_date.strftime("%Y-%m")
        try:
            text = pdf_text(download(n.url))
        except Exception as e:
            coverage.append(dict(month=month, title=n.title, status=f"download/ocr failed: {e}"))
            continue
        if probe_left and n.language.lower().startswith("eng"):
            probe(text, pats, n.title)
            probe_left -= 1
        sec = notice_section(text)
        parts = split_by_branch(sec, pats)
        status = "rules"
        if not parts:
            ai = ai_split(sec)
            if ai:
                status = "ai"
                lookup = {name.upper(): (name, code, dist) for _, name, code, dist in pats}
                for bname, cnt in ai:
                    name, code, dist = lookup.get(bname.upper(), (bname, "", None))
                    rows.append(dict(month=month, branch=name, branch_code=code, district=dist,
                                     edition_district=n.edition_district, accounts=cnt, method="ai"))
            else:
                status = "no branch found" if sec else "no Manappuram notice found"
        new = 0
        for name, code, dist, loans in parts:
            fresh = loans - seen_loans[month]
            seen_loans[month] |= loans
            new += len(fresh)
            if fresh:
                rows.append(dict(month=month, branch=name, branch_code=code, district=dist,
                                 edition_district=n.edition_district, accounts=len(fresh), method="rules"))
        coverage.append(dict(month=month, title=n.title, language=n.language,
                             edition_district=n.edition_district, status=status,
                             branches=len(parts), new_accounts=new))

    cov = pd.DataFrame(coverage)
    cov.to_csv(PROCESSED / "gold_auctions_coverage.csv", index=False)
    if not rows:
        print("gold auctions: no accounts parsed; see gold_auctions_coverage.csv")
        print(cov.status.value_counts().to_string() if len(cov) else "")
        return
    df = pd.DataFrame(rows)
    by_branch = (df.groupby(["month", "district", "branch", "branch_code"], dropna=False)["accounts"]
                 .sum().reset_index())
    by_branch.to_csv(PROCESSED / "gold_auctions_branch_monthly.csv", index=False)
    dist = (df.dropna(subset=["district"]).groupby(["district", "month"])
            .agg(auction_accounts=("accounts", "sum"), auction_branches=("branch", "nunique"))
            .reset_index())
    dist["v1_district"] = dist["district"].isin(DISTRICTS)
    dist.to_csv(PROCESSED / "gold_auctions_monthly.csv", index=False)
    print(f"gold auctions: {int(df.accounts.sum())} accounts, {df.branch.nunique()} branches, "
          f"{dist.district.nunique()} districts, months {dist.month.min()}..{dist.month.max()}")
    print(cov.status.value_counts().to_string())
    print(dist[dist.v1_district].pivot(index="month", columns="district", values="auction_accounts")
          .fillna(0).astype(int).to_string())


if __name__ == "__main__":
    main()
