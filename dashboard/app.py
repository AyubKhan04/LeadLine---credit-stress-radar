"""Phase 7: Streamlit dashboard.

Run:  streamlit run dashboard/app.py
Map (Folium), trend, "why" breakdown, what-if sliders, language picker
(English, Tamil, Hindi, Telugu, Malayalam, Kannada), AI monthly note and
"ask the data" when they exist.
"""
import json
import sys
from pathlib import Path

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.config import DISTRICTS, PROCESSED  # noqa: E402
from src.index.stress_index import WEIGHTS, BANDS  # noqa: E402

LANGS = ["en", "ta", "hi", "te", "ml", "kn"]
BAND_COLOURS = {"Low": "#2e7d32", "Watch": "#f9a825", "High": "#ef6c00", "Severe": "#c62828"}

st.set_page_config(page_title="Credit Stress Radar", page_icon="📡", layout="wide")


@st.cache_data
def load_lang(code):
    return json.loads((ROOT / "i18n" / f"{code}.json").read_text(encoding="utf-8"))


@st.cache_data
def load_index():
    return pd.read_csv(PROCESSED / "stress_index_monthly.csv").dropna(subset=["stress_index"])


@st.cache_data
def load_notes():
    p = PROCESSED / "ai_notes.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


names = {c: load_lang(c)["_language_name"] for c in LANGS}
lang = st.sidebar.selectbox("🌐 Language / மொழி", LANGS, format_func=names.get)
t = load_lang(lang)
en = load_lang("en")
tr = lambda k: t.get(k, en.get(k, k))  # noqa: E731

idx = load_index()
months = sorted(idx.month.unique())
month = st.sidebar.select_slider(tr("month"), months, value=months[-1])
district = st.sidebar.selectbox(tr("district"), list(DISTRICTS))

st.title(tr("app_title"))
st.caption(tr("subtitle"))

cur = idx[idx.month == month].set_index("district")
row = cur.loc[district] if district in cur.index else None

left, right = st.columns([3, 2])
with left:
    st.subheader(tr("map_title"))
    m = folium.Map(location=[11.2, 78.6], zoom_start=7, tiles="OpenStreetMap")
    for d, (lat, lon) in DISTRICTS.items():
        if d not in cur.index:
            continue
        r = cur.loc[d]
        folium.CircleMarker(
            [lat, lon], radius=10 + r.stress_index / 4, color=BAND_COLOURS[r.band], fill=True,
            fill_opacity=0.75, weight=2 if d == district else 1,
            tooltip=f"{d}: {r.stress_index:.0f} ({tr(r.band)})",
        ).add_to(m)
    st_folium(m, height=430, use_container_width=True, returned_objects=[])

with right:
    if row is None:
        st.info("No score for this month.")
    else:
        st.metric(f"{tr('stress_index')} · {district}", f"{row.stress_index:.0f} / 100",
                  help=tr("data_note"))
        st.markdown(f"**{tr('band')}:** <span style='color:{BAND_COLOURS[row.band]}'>"
                    f"■ {tr(row.band)}</span>", unsafe_allow_html=True)
        st.subheader(tr("components_title"))
        comp = pd.DataFrame({
            "component": [tr(c) for c in WEIGHTS],
            "points": [row[f"pts_{c}"] for c in WEIGHTS],
            "score": [row[f"score_{c}"] for c in WEIGHTS],
        }).dropna()
        fig = px.bar(comp.sort_values("points"), x="points", y="component", orientation="h",
                     hover_data={"score": ":.0f"}, height=260)
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), xaxis_title="", yaxis_title="")
        st.plotly_chart(fig, width="stretch")

st.subheader(tr("trend_title"))
h = idx[idx.district == district]
fig = px.line(h, x="month", y="stress_index", height=280)
for lo, band in BANDS:
    if lo:
        fig.add_hline(y=lo, line_dash="dot", line_color=BAND_COLOURS[band], opacity=0.5)
fig.add_vline(x=month, line_color="#555")
fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), yaxis_range=[0, 100], xaxis_title="", yaxis_title="")
st.plotly_chart(fig, width="stretch")

if row is not None:
    st.subheader(tr("whatif_title"))
    st.caption(tr("whatif_help"))
    cols = st.columns(3)
    new = {}
    for i, c in enumerate(WEIGHTS):
        base = row[f"score_{c}"]
        if pd.isna(base):
            continue
        new[c] = cols[i % 3].slider(tr(c), 0, 100, int(round(base)), key=f"wi_{c}_{district}_{month}")
    w = sum(WEIGHTS[c] for c in new)
    after = sum(new[c] * WEIGHTS[c] for c in new) / w if w else float("nan")
    a, b = st.columns(2)
    a.metric(tr("before"), f"{row.stress_index:.0f}")
    b.metric(tr("after"), f"{after:.0f}", delta=f"{after - row.stress_index:+.0f}", delta_color="inverse")

notes = load_notes()
note = notes.get(month, {}).get(lang) or notes.get(month, {}).get("en")
st.subheader(tr("ai_note"))
st.write(note if note else tr("no_note"))

try:
    from src.ai.ask import answer, available
    if available():
        st.subheader(tr("ask_title"))
        q = st.text_input(tr("ask_placeholder"), key="ask")
        if st.button(tr("ask_button")) and q:
            with st.spinner("…"):
                st.write(answer(q, lang))
except ImportError:
    pass

st.divider()
st.caption(tr("data_note"))
