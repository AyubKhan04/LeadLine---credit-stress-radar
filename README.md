# LeadLine - Credit Stress Radar

Early-warning system for household credit stress in Tamil Nadu. It builds a district-level 0-100 stress index from public signals like gold loan auctions, loan app complaints, search trends, rainfall and gold prices. It includes a risk score API, a map dashboard and AI credit notes in Tamil, English and other Indian languages.

**v1 scope:** Chennai, Coimbatore, Madurai, Villupuram. Monthly, January 2019 to now.

## Status

| Phase | What | State |
|---|---|---|
| 1 | Context data: rainfall, gold price, repo rate | done |
| 2 | Alternative data: Google Trends, loan-app reviews | done |
| 3 | Gold auction notice scraper (Manappuram, OCR) | done, short history |
| 4 | Analysis: seasonality, lead-lag, Granger, known stress periods | done: [docs/analysis.md](docs/analysis.md) |
| 5 | Stress index 0-100 with "why" breakdown | done |
| 6 | FastAPI score API | done |
| 7 | Streamlit map dashboard (6 languages, what-if) + Power BI files | done |
| 8 | AI monthly note, anomaly flags, monthly refresh, ask-the-data | done (AI parts need an API key) |

## Layout

```
data/raw/          downloads, OCR text, review text (git-ignored: may hold personal details)
data/processed/    tidy monthly CSVs, index, flags, notes (committed)
data/powerbi/      star-schema CSVs for Power BI
src/collectors/    one script per source (gold_auctions.py = phase 3)
src/classify/      review complaint classifier (rules + optional AI: Gemini free tier or Claude)
src/analysis/      panel builder + phase 4 analysis (writes docs/analysis.md)
src/index/         stress index (phase 5) and Power BI export
src/api/           FastAPI app (phase 6)
src/ai/            anomaly flags, monthly note, ask-the-data (phase 8)
dashboard/app.py   Streamlit dashboard (phase 7)
i18n/              UI text: en, ta, hi, te, ml, kn
docs/              analysis write-up, Power BI guide, LinkedIn draft
run_collectors.py  runs collectors; one failing source doesn't stop the rest
```

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env              # optional: GEMINI_API_KEY (free) turns on the AI parts
python run_collectors.py          # phase 1-2 sources (add gold_auctions for phase 3; needs tesseract)
python -m src.analysis.explore    # phase 4 -> docs/analysis.md
python -m src.index.stress_index  # phase 5 -> data/processed/stress_index_monthly.csv
python -m src.ai.anomaly          # anomaly flags
python -m src.ai.notes            # monthly note (rules; AI rewrites it in 6 languages if a key is set)
python -m src.index.powerbi_export
uvicorn src.api.main:app --reload # API docs at http://127.0.0.1:8000/docs
streamlit run dashboard/app.py    # dashboard
```

GitHub Actions: `monthly-refresh.yml` runs all of that on the 5th of each month and commits
the results (also runnable by hand from the Actions tab). `collect-data.yml` and
`collect-auctions.yml` can be run by hand (Actions tab > Run workflow); `collect-data.yml` also runs when collector code changes on a `claude/` branch.
## AI features for free (Gemini)

Everything runs without AI: the monthly note falls back to a rules-based English note and
the review classifier to keyword rules. To turn on AI notes in 6 languages, "ask the data"
and the AI review classifier **at no cost**, use Google's Gemini free tier:

1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey) and sign in with a Google account.
2. Click **Create API key** (pick or create any project). No card or billing is needed.
3. Copy the key. On GitHub open the repo, then **Settings > Secrets and variables > Actions >
   New repository secret**. Name it `GEMINI_API_KEY`, paste the key, then click **Add secret**.
4. For running on your own computer, put the same key in `.env` as `GEMINI_API_KEY=...`.

Notes on the free tier (checked Nov 2026):
- **Limits:** there are per-minute and per-day request limits, shown in AI Studio. This project makes about 20-40 calls a month, well inside them, and the code waits and retries when it hits a per-minute limit.
- **Your prompts:** Google may use free-tier prompts to improve its products, and people may review them. So the OCR text of auction notices, which can contain personal details, is **never** sent to Gemini. Only the index summary and public app-store review text are.
- **Claude (paid):** Claude still works if you set `ANTHROPIC_API_KEY` instead. It is the only provider the auction-notice fallback will use. Use `LEADLINE_AI_PROVIDER=gemini|anthropic|none` to force a choice.

## Gold auction notices (phase 3)

`gold_auctions_monthly.csv` (district x month), `gold_auctions_branch_monthly.csv`,
`gold_auctions_coverage.csv` (one row per newspaper page: parsed or why not).

- **Source:** [Manappuram Finance auction publications](https://www.manappuram.com/auction-publications),
  filtered to Tamil Nadu: scanned newspaper pages (Dinamani, The New Indian Express;
  8 editions) carrying each gold auction notice. robots.txt allows these pages and the
  terms don't forbid reuse. Requests are spaced 1.5 s apart with an identifying User-Agent.
- **Method:** Tesseract OCR at 450 dpi, cut out the Manappuram notice, anchor on district
  names ("DISTRICT, BRANCH, loan number, ..."), count distinct loan numbers per district
  and month (the same notice runs in several papers, so numbers are de-duplicated). If no
  district is found and `ANTHROPIC_API_KEY` is set, Claude returns branch counts (never sent to Gemini's free tier).
- **Privacy:** only counts are committed. Loan numbers and anything else OCR reads stay
  in git-ignored `data/raw/` and the Actions cache.

## The stress index (phase 5)

Each month every district gets a 0-100 score. Each signal is turned into a 0-100
sub-score (its percentile against the district's own past, so no look-ahead), then
weighted. Missing signals drop out and the rest are re-weighted.

| Component | Weight | Signal |
|---|---|---|
| Pawn searches | 30 | Tamil searches "நகை அடகு", "நகை கடன்", year on year |
| Rainfall | 20 | two-tailed rainfall z-score vs the same calendar month, mean of last 4 months |
| Gold auctions | 20 | Manappuram auction accounts in the district (when notices exist) |
| Digital credit | 15 | instant loan / loan app searches year on year, loan-app complaint share |
| Rates | 10 | repo rate plus hikes in the last 12 months |
| Gold price | 5 | falling gold price (loans go under water) |

Bands: Low < 40, Watch 40-60, High 60-75, Severe 75+. The `why` column names the
components scoring 65+. Weights are set by judgement guided by [phase 4](docs/analysis.md),
not fitted, because there is no ground-truth stress series to fit to.

**Backtest** (`data/processed/stress_index_backtest.csv`, as of 26 Nov 2026): the index ran
High during the Delta wave (mean 60, peak 79) and in Chennai after Cyclone Michaung
(mean 63, peak 78), but it did **not** flag the 2020 lockdown (mean 40) or the Villupuram
floods after Cyclone Fengal (mean 43). Searches for pawning fell when branches were shut,
and the rainfall signal averages over 4 months. These are listed as gaps below.

## API (phase 6)

`GET /districts` latest score per district · `GET /score/{district}?month=YYYY-MM` score,
band, reason and component breakdown · `GET /history/{district}` · `POST /whatif`
with `{"district": "Madurai", "scores": {"rain": 90}}` re-scores with changed components.

## Data sources (phases 1-2)

| File | Source | Licence / terms | Grain |
|---|---|---|---|
| `rainfall_monthly.csv` | [Open-Meteo historical archive](https://open-meteo.com/en/docs/historical-weather-api) (ERA5 reanalysis) at each district HQ | CC BY 4.0, free non-commercial | district x month |
| `gold_monthly.csv` | [World Bank Pink Sheet](https://www.worldbank.org/en/research/commodity-markets) gold USD/oz x USD/INR from [FRED EXINUS](https://fred.stlouisfed.org/series/EXINUS), falling back to ECB reference rates | CC BY 4.0 / public | national x month |
| `repo_rate_monthly.csv` | RBI Monetary Policy press releases (change dates kept in `repo_rate.py`) | public | national x month |
| `trends_tn_monthly.csv` | Google Trends via pytrends, geo IN-TN | unofficial API; robots.txt only blocks the `/explore?` web page | state x month x term |
| `play_reviews_dataset_monthly.csv` | [SLICE PAY App Reviews](https://www.kaggle.com/datasets/pavan9065/slice-pay-app-reviews) on Kaggle: Google Play reviews of the slice credit app | CC0 public domain | month |
| `app_reviews_monthly.csv`, `app_reviews_monthly_by_app.csv` | Apple App Store public review RSS feed (India), 12 lending and gold-loan apps | public feed; only counts are committed | month (x app) |

Every collector checks robots.txt before fetching and sends an identifying User-Agent at low volume.
One note: Open-Meteo's API host has a robots.txt that blocks all crawlers. Its API is documented for
programmatic use under its own terms, so we use it (4 requests per run) and log the robots result.

## Coverage from the first full run (26 Nov 2026)

| Dataset | Rows | Months | Notes |
|---|---|---|---|
| Rainfall | 380 | 2019-01 to 2026-11, all 4 districts | Nov 2026 partial (26 days), its anomaly is left blank |
| Gold (INR/10g) | 94 | 2019-01 to 2026-10 | Nov 2026 arrives with the World Bank's early-December update. FRED timed out from GitHub's runners, so FX came from the ECB fallback |
| Repo rate | 95 | 2019-01 to 2026-11 | 19 rate changes, latest 5.50% from 7 Oct 2026 |
| Google Trends (TN) | 475 | 2019-01 to 2026-11, 5 terms | English terms have no zero months. Tamil terms are thin: "நகை அடகு" is zero in 39 of 95 months, "நகை கடன்" in 14 |
| Play reviews dataset (slice) | 150,444 reviews | 2019-01 to 2022-08 | 3,279 stress complaints (2.4% of reviews a month on average): fraud 2,052, hidden charges 861, harassment 367, threats 248, recovery agents 86. Only 13 Tamil-script reviews |
| App reviews (Apple feed) | 150 reviews | 2026-10 to 2026-11 only | Only 2 of 12 apps (Navi, Fibe) have reviews in Apple's India feed |

### Complaint labels

`harassment`, `threats`, `hidden_charges`, `recovery_agents`, `fraud`. Keyword rules in English, Tamil script and some Tanglish run first. If `GEMINI_API_KEY` (free) or `ANTHROPIC_API_KEY` is set, low-star (1-2) reviews the rules missed go to the AI model in batches of 20, capped at 300 reviews per run (free on Gemini). Without a key the AI step is skipped and everything still runs. Reviews rated 4-5 stars are never counted as complaints (in the slice data, "fraud" in a 5-star review usually means "unlike fraud apps").

To rebuild the slice numbers, put `slicepay_reviews.csv` in `data/raw/` (Kaggle needs a login to download), or add `KAGGLE_USERNAME` and `KAGGLE_KEY` as repository secrets so the workflow fetches it. Reviewer names and ids are never loaded.

## Known gaps and caveats (honest list)

- **Auction history is short: April to October 2026.** Manappuram only keeps recent notices online. IIFL's robots.txt blocks its auction list beyond page one (`Disallow: /auction?*`) and Muthoot doesn't post notices online, so neither is used. Older notices exist only in newspaper archives (paid). The monthly workflow adds each new month, so the series grows from here.
- **The committed counts come from a first OCR pass at the scan's native resolution** (about 2,000 accounts across 29 districts), which misses many loan numbers. The collector now OCRs at 450 dpi, but that takes about a minute per page, so it works through the pages within a 60-minute budget each run and caches the text. The monthly refresh catches up over its first couple of runs.
- **Auction counts are a floor, not a census.** OCR of small newspaper type misses some loan numbers, and a district only appears when its name is read correctly. Use the trend within a district, not exact totals. The branch list from Manappuram's branch locator returns only one branch per district, so branch-to-district mapping comes from the notice text itself.

- **The index has no ground truth.** No public monthly district series of household credit stress exists, so phase 4 uses Tamil pawn searches as the yardstick and the weights are judgement, not fitted. Treat scores as a ranking of "how unusual is this month for this district", not a default probability.
- **It missed two known episodes** (2020 lockdown, Cyclone Fengal in Villupuram), see the backtest above. Search signals fall when access to branches stops.
- **State-level signals dominate.** Trends, gold, rates and app reviews are the same for every district; only rainfall and auctions vary by district, so districts move together.
- **The latest month is partial** (Trends and rainfall for the current month are incomplete; gold lags a month).
- **Translations** for hi, te, ml and kn were drafted without native-speaker review.

- **Rainfall is not IMD.** IMD district rainfall on data.gov.in needs an API key and its open district series ends years ago. Open-Meteo is modelled grid data at one point per district, not a gauge average over the district. The "normal" for anomalies is the 2019-now mean per calendar month, a short baseline (IMD normals use 1971-2020).
- **Gold is the international price in rupees,** without import duty and GST, so it sits below IBJA/retail rates. Levels differ; month-on-month moves track closely. IBJA has no open API. The World Bank file updates early each month and FRED's FX series lags about a month, so the newest month can be missing.
- **Repo rate is a hand-kept table.** Add a row after each MPC meeting that changes the rate (next one early December 2026).
- **Google Trends has no district signal.** Google gives no city time series for India, and the city breakdown inside Tamil Nadu came back empty for every term and year, so Trends is a state-level series only. Values are 0-100 relative within each term. Tamil-script terms have low volume and can come back empty. pytrends is unofficial and Google rate-limits it; failed calls are listed in `trends_failures.csv`.
- **Google Play reviews are not collected.** play.google.com/robots.txt disallows `/_/` and `/store/getreviews`, the endpoints review scrapers (including google-play-scraper) use. Apple's feed is used instead, which means: far fewer reviews (iPhone share in India is small; 10 of 12 apps returned none), mostly English, and at most the latest 500 reviews per app, so history only goes back weeks or months, not to 2019. On its own it is too thin to drive the index.
- **The Play review dataset covers one app and stops in August 2022.** No openly licensed dataset of Indian loan-app Play reviews from 2023 on was found (Kaggle, Hugging Face, Mendeley searched in Nov 2026). slice is a credit-card/BNPL app used mostly by students and young earners, not a gold-loan or payday lender, so it shows digital-credit stress, not rural jewel-loan stress. Volume jumps from about 1,000 to 20,000 reviews a month in 2022, so use the complaint share, not raw counts. There's a gap from Sep 2022 to Sep 2026 between this dataset and the Apple feed. Reviews carry no location, so this is a state/national signal, not a district one.
- **No personal data is stored in git.** Reviewer names and ids are never read; review text stays in git-ignored `data/raw/`.

See `data/processed/last_run_log.txt` for the latest run's coverage.
