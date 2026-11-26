"""Preview of the WhatsApp-style alert a field officer would get when a district jumps."""
import html
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import language_picker, load_csv, load_index, load_secrets  # noqa: E402

st.set_page_config(page_title="Alerts - Credit Stress Radar", page_icon="🔔", layout="wide")
load_secrets()
lang, tr = language_picker()
st.title("🔔 Alert preview")
st.caption("What a branch or field officer would receive when a district's score jumps or moves up a level. "
           "This is a preview only: nothing is sent.")

flags = load_csv("anomaly_flags.csv")
idx = load_index().set_index(["district", "month"])
jumps = flags[flags.flag.isin(["index_jump", "band_up"])]
if jumps.empty:
    st.info("No jumps flagged yet.")
    st.stop()

events = jumps.groupby(["district", "month"]).size().reset_index()[["district", "month"]]
events = events.sort_values("month", ascending=False)
labels = [f"{r.month} · {r.district}" for r in events.itertuples()]
pick = st.selectbox("Alert", range(len(events)), format_func=lambda i: labels[i])
ev = events.iloc[pick]
r = idx.loc[(ev.district, ev.month)]
months = sorted(idx.xs(ev.district).index)
prev_m = months[months.index(ev.month) - 1] if months.index(ev.month) else None
prev = idx.loc[(ev.district, prev_m)].stress_index if prev_m else None

lines = [f"⚠️ *{tr('app_title')}*",
         f"*{ev.district}* · {ev.month}",
         f"{tr('stress_index')}: *{r.stress_index:.0f}*" + (f" (was {prev:.0f})" if prev is not None else ""),
         f"{tr('band')}: *{tr(r.band)}*",
         f"{tr('why')}: {r.why}"]
for d in jumps[(jumps.district == ev.district) & (jumps.month == ev.month)].detail:
    lines.append(f"• {d}")
lines.append("_Reply STOP to unsubscribe_")


def wa(text):  # WhatsApp *bold* and _italic_
    import re
    t = html.escape(text)
    t = re.sub(r"\*(.+?)\*", r"<b>\1</b>", t)
    return re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<i>\1</i>", t)


body = "<br>".join(wa(x) for x in lines)
st.markdown(f"""
<div style="max-width:380px;background:#e5ddd5;border-radius:14px;padding:14px;font-family:sans-serif">
  <div style="background:#075e54;color:#fff;border-radius:10px 10px 0 0;margin:-14px -14px 12px;padding:10px 14px">
    <b>📡 Stress Radar</b><br><span style="font-size:12px;opacity:.8">alerts · {html.escape(ev.district)}</span>
  </div>
  <div style="background:#fff;color:#111;border-radius:0 10px 10px 10px;padding:10px 12px;font-size:14px;
              line-height:1.45;box-shadow:0 1px 1px rgba(0,0,0,.15)">{body}
    <div style="text-align:right;font-size:11px;color:#999;margin-top:4px">09:00 ✓✓</div>
  </div>
</div>""", unsafe_allow_html=True)

with st.expander("Plain text (copy into WhatsApp)"):
    st.code("\n".join(lines), language=None)
st.caption("Sending for real would need the WhatsApp Business API, which is paid, so this project stops at the preview.")
