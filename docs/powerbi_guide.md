# Build the Power BI version (about 30 minutes)

You need Power BI Desktop (free, Windows). The data comes from `data/powerbi/`,
refreshed by `python -m src.index.powerbi_export` or the monthly GitHub Action.

## 1. Load the data
1. **Home > Get data > Text/CSV**, and load all five files in `data/powerbi/`.
2. In **Model view**, drag to make these relationships (many-to-one, single direction):
   - `fact_stress[district]` → `dim_district[district]`
   - `fact_stress[month]` → `dim_date[month]`
   - `fact_signals[district]` → `dim_district[district]`
   - `fact_signals[month]` → `dim_date[month]`
3. In `dim_date`, select `month_name` and use **Sort by column > month_num**.
4. Set `dim_district[latitude]` and `[longitude]` data category to Latitude / Longitude.

## 2. Measures (Home > New measure)
```DAX
Stress Index = AVERAGE(fact_stress[stress_index])
Latest Month = MAX(fact_stress[month])
Stress Latest =
    CALCULATE([Stress Index], fact_stress[month] = [Latest Month])
Change vs Last Year =
    VAR m = MAX(dim_date[date])
    RETURN [Stress Index] - CALCULATE([Stress Index], SAMEPERIODLASTYEAR(dim_date[date]))
Band Colour =
    SWITCH(TRUE(), [Stress Index] >= 75, "#C62828", [Stress Index] >= 60, "#EF6C00",
                   [Stress Index] >= 40, "#F9A825", "#2E7D32")
```
(`SAMEPERIODLASTYEAR` needs `dim_date` marked as a date table: **Table tools > Mark as date table**, column `date`.)

## 3. Page layout
- **Map** (Azure map or Map visual): latitude/longitude from `dim_district`, bubble size
  `Stress Index`, bubble colour via **Conditional formatting > Field value > Band Colour**.
- **Card**: `Stress Latest`. **Card**: `Change vs Last Year`.
- **Line chart**: x `dim_date[date]`, y `Stress Index`, legend `dim_district[district]`.
  Add constant lines at 40, 60 and 75 (Analytics pane).
- **Stacked bar** "why": y `dim_district[district]`, x the `pts_*` columns of `fact_stress`
  (rename them in the Fields pane to the labels in `dim_component.csv`).
- **Table**: `district`, `month`, `stress_index`, `band`, `why`.
- **Slicers**: `dim_date[year]`, `dim_district[district]`.

## 4. What-if (optional)
**Modeling > New parameter > Numeric range**, name `Rain shock`, 0 to 100, default 50. Then:
```DAX
Stress What-if =
    VAR w = 20
    RETURN [Stress Index] + w * ('Rain shock'[Rain shock Value] - AVERAGE(fact_stress[score_rain])) / 100
```
Put `Stress Index` and `Stress What-if` side by side on cards.

## 5. Compare with Streamlit
Screenshot both and keep whichever reads better for the portfolio. Streamlit is
easier to share as a link (Streamlit Community Cloud); Power BI looks more familiar to
bank and BFSI recruiters.
