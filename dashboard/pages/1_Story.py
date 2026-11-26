"""The story in 60 seconds: four findings, with the weak ones called weak."""
import sys
from pathlib import Path

import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import load_csv, load_index, load_secrets  # noqa: E402
from src.analysis.explore import EPISODES  # noqa: E402

st.set_page_config(page_title="Story - Credit Stress Radar", page_icon="📖", layout="wide")
load_secrets()
st.title("📖 The story in 60 seconds")
st.caption("Four findings from 2020 to now. Each one says how much to trust it.")

idx = load_index()
bt = load_csv("stress_index_backtest.csv")
ll = load_csv("analysis_lead_lag.csv")
panel = load_csv("panel_monthly.csv")
auc = load_csv("gold_auctions_monthly.csv")


def shade(fig, where=None):
    for name, a, b, w, _ in EPISODES:
        if where and w not in ("all", where):
            continue
        fig.add_vrect(x0=a, x1=b, fillcolor="grey", opacity=0.15, line_width=0,
                      annotation_text=name, annotation_position="top left", annotation_font_size=10)
    return fig


# 1 -------------------------------------------------------------------------
st.header("1. The index rises in most known stress episodes, but it missed the first lockdown")
fig = px.line(idx, x="month", y="stress_index", color="district", height=360)
for y in (40, 60, 75):
    fig.add_hline(y=y, line_dash="dot", line_color="grey", opacity=0.5)
st.plotly_chart(shade(fig), width="stretch")
if len(bt):
    d = bt.set_index("episode")
    c, dl = d.loc["COVID lockdown"], d.loc["Delta wave"]
    st.markdown(
        f"During the **Delta wave** the average score was **{dl.mean_index:.0f}** (peak {dl.peak_index:.0f}), "
        f"well above the usual level. During the **first COVID lockdown** it was only **{c.mean_index:.0f}**. "
        "So the index caught the second shock and missed the first. **Trust: medium.** "
        "These are five episodes, not a proper test.")

# 2 -------------------------------------------------------------------------
st.header("2. Pawn searches *fell* in the 2020 lockdown, then jumped")
if len(panel):
    s = panel.groupby("month")[["trends_nagai_adagu", "trends_nagai_kadan"]].mean().mean(axis=1)
    s = s.rolling(3, min_periods=1).mean().rename("Tamil pawn searches (3-month avg)").reset_index()
    fig = px.line(s, x="month", y=s.columns[1], height=300)
    fig.add_vrect(x0="2020-04", x1="2020-06", fillcolor="grey", opacity=0.2, line_width=0,
                  annotation_text="lockdown", annotation_position="top left")
    st.plotly_chart(fig, width="stretch")
st.markdown("Pawn shops and bank branches were shut, so people stopped searching for them, and searches came "
            "back once they reopened. Search data shows **intent to borrow when borrowing is possible**, "
            "not hardship itself. That is why the index missed the first lockdown. **Trust: high** for the "
            "pattern, but it is one event.")

# 3 -------------------------------------------------------------------------
st.header("3. Rainfall may lead pawn searches by a few months. This is only a hint")
if len(ll):
    g = ll.assign(signal=ll.granger_p < 0.05)
    fig = px.bar(g, x="driver", y="granger_p", color="signal", height=300,
                 color_discrete_map={True: "#ef6c00", False: "#9e9e9e"},
                 labels={"granger_p": "Granger p-value (lower = stronger)", "driver": ""})
    fig.add_hline(y=0.05, line_dash="dash", annotation_text="p = 0.05")
    fig.update_layout(showlegend=False)
    st.plotly_chart(fig, width="stretch")
    r = ll.set_index("driver").loc["rain_deficit"]
    st.markdown(
        f"On today's data, rainfall gives p = **{r.granger_p:.3f}** at a {int(r.granger_best_lag)}-month lead. "
        "But this p-value has moved between about 0.01 and 0.12 as each month's data was added. A result that "
        "moves that much is not settled. **Trust: low.** It is a reason to keep watching rainfall, not proof.")

# 4 -------------------------------------------------------------------------
st.header("4. Gold auctions are spread across the state, not just the big cities")
if len(auc):
    top = auc.groupby("district").auction_accounts.sum().sort_values(ascending=False).head(12).reset_index()
    fig = px.bar(top, x="auction_accounts", y="district", orientation="h", height=380,
                 labels={"auction_accounts": "gold loan accounts put up for auction", "district": ""})
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(fig, width="stretch")
    st.markdown(f"From one lender's public notices, {auc.month.min()} to {auc.month.max()}: "
                f"**{int(auc.auction_accounts.sum()):,} accounts** in **{auc.district.nunique()} districts**. "
                "Counts come from scanned PDFs, so they are a floor, and one lender is not the market. "
                "**Trust: medium** for where, low for how many.")

st.divider()
st.caption("What this is not: there is no official district default data in the index, so none of this is "
           "checked against real loan losses yet. See the Validation section in the README.")
