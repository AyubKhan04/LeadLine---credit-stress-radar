# LeadLine - Credit Stress Radar

Early-warning system for household credit stress in Tamil Nadu. It builds a district-level 0-100 stress index from public signals like gold loan auctions, loan app complaints, search trends, rainfall and gold prices. It includes a risk score API, a map dashboard and AI credit notes in Tamil, English and other Indian languages.

**v1 scope:** Chennai, Coimbatore, Madurai, Villupuram. Monthly, January 2019 to now.

## Status

| Phase | What | State |
|---|---|---|
| 1 | Context data: rainfall, gold price, repo rate | done |
| 2 | Alternative data: Google Trends, loan-app reviews | done |
| 3 | Gold auction notice scraper | next |
| 4-8 | Analysis, index, API, dashboard, AI notes | planned |

## Layout

```
data/raw/          downloads and review text (git-ignored: may hold personal details)
data/processed/    tidy monthly CSVs (committed)
src/collectors/    one script per source
src/classify/      review complaint classifier (rules + optional Claude Haiku)
src/config.py      districts, date range, robots.txt check
i18n/              UI strings per language (en, ta) for the later language picker
notebooks/         analysis (phase 4)
run_collectors.py  runs every collector; one failing source doesn't stop the rest
```

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env          # optional: add ANTHROPIC_API_KEY for the AI classifier
python run_collectors.py      # or: python run_collectors.py gold trends
```

The GitHub Actions workflow `collect-data.yml` runs the same thing and commits refreshed CSVs.
To use the AI classifier there, add `ANTHROPIC_API_KEY` as a repository secret.

## Data sources (phases 1-2)

| File | Source | Licence / terms | Grain |
|---|---|---|---|
| `rainfall_monthly.csv` | [Open-Meteo historical archive](https://open-meteo.com/en/docs/historical-weather-api) (ERA5 reanalysis) at each district HQ | CC BY 4.0, free non-commercial | district x month |
| `gold_monthly.csv` | [World Bank Pink Sheet](https://www.worldbank.org/en/research/commodity-markets) gold USD/oz x [FRED EXINUS](https://fred.stlouisfed.org/series/EXINUS) USD/INR | CC BY 4.0 / public domain | state x month |
| `repo_rate_monthly.csv` | RBI Monetary Policy press releases (change dates kept in `repo_rate.py`) | public | national x month |
| `trends_tn_monthly.csv` | Google Trends via pytrends, geo IN-TN | unofficial API; robots.txt only blocks the `/explore?` web page | state x month x term |
| `trends_tn_city_yearly.csv` | Google Trends city breakdown inside Tamil Nadu | as above | city x year x term |
| `app_reviews_monthly.csv`, `app_reviews_monthly_by_app.csv` | Apple App Store public review RSS feed (India), 12 lending and gold-loan apps | public feed; only counts are committed | month (x app) |

Every collector checks robots.txt before fetching and sends an identifying User-Agent at low volume.

### Complaint labels

`harassment`, `threats`, `hidden_charges`, `recovery_agents`, `fraud`. Keyword rules in English, Tamil script and some Tanglish run first. If `ANTHROPIC_API_KEY` is set, low-star (1-2) reviews the rules missed go to `claude-haiku-5-5` in batches of 20, capped at 300 reviews per run (well under a cent at Haiku prices). Without a key the AI step is skipped and everything still runs.

## Known gaps and caveats (honest list)

- **Rainfall is not IMD.** IMD district rainfall on data.gov.in needs an API key and its open district series ends years ago. Open-Meteo is modelled grid data at one point per district, not a gauge average over the district. The "normal" for anomalies is the 2019-now mean per calendar month, a short baseline (IMD normals use 1971-2020).
- **Gold is the international price in rupees,** without import duty and GST, so it sits below IBJA/retail rates. Levels differ; month-on-month moves track closely. IBJA has no open API. The World Bank file updates early each month and FRED's FX series lags about a month, so the newest month can be missing.
- **Repo rate is a hand-kept table.** Add a row after each MPC meeting that changes the rate (next one early December 2026).
- **Google Trends has no city time series for India.** We get a Tamil Nadu monthly series per term, and yearly city cross-sections, which only cover cities Google ranks (smaller ones like Villupuram may be missing). Values are 0-100 relative within each term. Tamil-script terms have low volume and can come back empty. pytrends is unofficial and Google rate-limits it; failed calls are listed in `trends_failures.csv`.
- **Google Play reviews are not collected.** play.google.com/robots.txt disallows `/_/` and `/store/getreviews`, the endpoints review scrapers (including google-play-scraper) use. Apple's feed is used instead, which means: far fewer reviews (iPhone share in India is small), mostly English, and at most the latest 500 reviews per app, so history only goes back months, not to 2019. Reviews carry no location, so this is a state/national signal, not a district one.
- **No personal data is stored in git.** Reviewer names and ids are never read; review text stays in git-ignored `data/raw/`.

See `data/processed/last_run_log.txt` for the latest run's coverage.
