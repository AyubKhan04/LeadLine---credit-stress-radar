# LinkedIn post (draft)

**Can public data warn us about household debt stress before the banks report it?**

I built **LeadLine, a Credit Stress Radar for Tamil Nadu**, to find out. It's an
early-warning index (0-100) for 4 districts (Chennai, Coimbatore, Madurai and
Villupuram), updated monthly from 2019 on, using only open signals:

🔎 Google searches in Tamil for pawning jewellery (நகை அடகு)
🌧️ Rainfall anomalies (drought *and* floods)
🪙 Gold auction notices: OCR'd from scanned newspaper pages, counts only, no personal data
📱 Instant-loan app searches and app-review complaints
🏦 Gold price and the RBI repo rate

What I learned:
• Rainfall deficits lead pawn searches by about 4 months (Granger test, p≈0.01).
• Pawn searches *fell* during the 2020 lockdown, because when branches shut, search signals go quiet. An index has to know its blind spots, so the README lists what it missed.
• Every score comes with a "why", and a what-if slider shows how a bad monsoon would move it.

Stack: Python · pandas · statsmodels · Tesseract OCR · FastAPI · Streamlit + Folium ·
Power BI · GitHub Actions (monthly refresh) · Claude Haiku for monthly notes in
6 Indian languages and "ask the data".

Code and write-up: <repo link>
Dashboard: <Streamlit link>

I'd love feedback from people in credit risk and BFSI analytics. What signal would you add?

#CreditRisk #DataScience #FinTech #Banking #TamilNadu #Python #PowerBI
