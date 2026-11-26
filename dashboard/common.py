"""Shared bits for the dashboard pages: paths, secrets, data loaders, translations."""
import json
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.config import DISTRICTS, PROCESSED  # noqa: E402,F401

LANGS = ["en", "ta", "hi", "te", "ml", "kn"]
BAND_COLOURS = {"Low": "#2e7d32", "Watch": "#f9a825", "High": "#ef6c00", "Severe": "#c62828"}
EPISODE_SHADE = "rgba(120,120,120,0.15)"


def load_secrets():
    """Streamlit Cloud keeps keys in st.secrets; the AI code reads os.environ. Copy them over."""
    for k in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "LEADLINE_AI_PROVIDER", "GEMINI_MODEL"):
        if os.environ.get(k):
            continue
        try:
            v = st.secrets.get(k)
        except Exception:  # no secrets.toml locally: fine, use .env / environment
            v = None
        if v:
            os.environ[k] = str(v)


@st.cache_data
def load_lang(code):
    return json.loads((ROOT / "i18n" / f"{code}.json").read_text(encoding="utf-8"))


@st.cache_data
def load_index():
    return pd.read_csv(PROCESSED / "stress_index_monthly.csv").dropna(subset=["stress_index"])


@st.cache_data
def load_csv(name):
    p = PROCESSED / name
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


@st.cache_data
def load_notes():
    p = PROCESSED / "ai_notes.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def language_picker():
    """Sidebar language picker shared by every page; returns tr(key)."""
    names = {c: load_lang(c)["_language_name"] for c in LANGS}
    keep = st.session_state.get("_lang", "en")  # survives page switches
    lang = st.sidebar.selectbox("🌐 Language / மொழி", LANGS, index=LANGS.index(keep), format_func=names.get)
    st.session_state["_lang"] = lang
    t, en = load_lang(lang), load_lang("en")
    return lang, (lambda k: t.get(k, en.get(k, k)))
