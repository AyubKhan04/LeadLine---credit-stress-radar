"""Shared settings for all collectors."""
from datetime import date
from pathlib import Path
import urllib.robotparser

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
RAW.mkdir(parents=True, exist_ok=True)
PROCESSED.mkdir(parents=True, exist_ok=True)

START = date(2019, 1, 1)
TODAY = date.today()

# v1 districts, with district HQ coordinates (used as the rainfall point)
DISTRICTS = {
    "Chennai": (13.0827, 80.2707),
    "Coimbatore": (11.0168, 76.9558),
    "Madurai": (9.9252, 78.1198),
    "Villupuram": (11.9401, 79.4861),
}

USER_AGENT = "LeadLine-research/0.1 (portfolio project; low volume)"


def robots_allows(url: str) -> bool:
    """Check robots.txt for the URL's host before fetching it.

    robots.txt is fetched with our own User-Agent: some hosts (Cloudflare) refuse
    Python's default urllib agent, which RobotFileParser.read() would then treat
    as "disallow everything".
    """
    from urllib.parse import urlparse
    import requests
    p = urlparse(url)
    robots = f"{p.scheme}://{p.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser(robots)
    try:
        r = requests.get(robots, headers={"User-Agent": USER_AGENT}, timeout=30)
        if r.status_code in (401, 403):
            print(f"[robots] {robots} refused us (HTTP {r.status_code}): treating as disallowed")
            return False
        rp.parse(r.text.splitlines() if r.ok else [])
    except Exception as e:  # robots.txt unreachable: treat as allowed but say so
        print(f"[robots] could not read robots.txt for {p.netloc}: {e}")
        return True
    ok = rp.can_fetch(USER_AGENT, url) and rp.can_fetch("*", url)
    print(f"[robots] {'allowed' if ok else 'DISALLOWED'}: {url}")
    return ok
