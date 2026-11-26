# Validation against real defaults (SLBC district NPA)

Source: Tamil Nadu SLBC quarterly agenda books (https://www.indianbank.in/slbc/), district-wise NPA %, typed into `data/external/slbc_tn_npa.csv`.

**Status: not validated yet.** Only 0 district-quarter NPA figures are entered; at least 8 (2 per district) are needed for even a rough check. Until then, the index is checked only against known stress episodes (see the README backtest), which is a weaker test.

How to add data: open a quarterly agenda PDF, find the district-wise NPA table, and add one row per v1 district (Chennai, Coimbatore, Madurai, Villupuram) to the CSV. Then run `python -m src.analysis.validate_npa`.
