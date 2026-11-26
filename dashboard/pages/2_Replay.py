"""Replay the map month by month, 2019 to now. Press play."""
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import BAND_COLOURS, DISTRICTS, language_picker, load_index, load_secrets  # noqa: E402

st.set_page_config(page_title="Replay - Credit Stress Radar", page_icon="⏯️", layout="wide")
load_secrets()
lang, tr = language_picker()
idx = load_index().copy()
st.title("⏯️ " + tr("map_title"))
st.caption(f"{idx.month.min()} to {idx.month.max()}. Press ▶ to replay every month. Watch for spring 2021 (Delta wave), 2022-23 (rate hikes) and "
           "Dec 2023 in Chennai (Cyclone Michaung floods). Bubble size and colour show the index.")

idx["lat"] = idx.district.map(lambda d: DISTRICTS[d][0])
idx["lon"] = idx.district.map(lambda d: DISTRICTS[d][1])
idx["size"] = idx.stress_index.clip(lower=5)
# one continuous colour scale stepped at the band edges, so every frame uses the same colours
c = BAND_COLOURS
scale = [(0, c["Low"]), (.4, c["Low"]), (.4, c["Watch"]), (.6, c["Watch"]), (.6, c["High"]),
         (.75, c["High"]), (.75, c["Severe"]), (1, c["Severe"])]

fig = px.scatter_map(
    idx.sort_values("month"), lat="lat", lon="lon", size="size", size_max=45, color="stress_index",
    color_continuous_scale=scale, range_color=(0, 100), labels={"stress_index": tr("stress_index")},
    animation_frame="month", hover_name="district",
    hover_data={"stress_index": ":.0f", "why": True, "lat": False, "lon": False, "size": False, "band": True},
    zoom=6, center={"lat": 11.4, "lon": 79.0}, map_style="open-street-map", height=600)
fig.layout.updatemenus[0].buttons[0].args[1]["frame"]["duration"] = 350
st.plotly_chart(fig, width="stretch")

with st.expander("Months at High or worse"):
    hi = idx[idx.stress_index >= 60].pivot_table(index="month", columns="district", values="stress_index")
    st.dataframe(hi.round(0), width="stretch")
