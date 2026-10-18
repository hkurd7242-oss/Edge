# Edge — Cross-Asset Intelligence (v2)

**Purpose:** a mobile-first, low-cost research workspace for crypto, gold/metals, macroeconomic releases, financial news, asymmetric-trade research, and deliberate trader education. Edge is a decision-support product, not an execution bot and not a price-prediction engine.

## Product principles

1. **Low recurring cost first.** No mandatory paid provider and no per-request LLM. Event explanations and learning content use transparent deterministic rules and a curated lesson library. Optional paid data should be added only when a documented data gap justifies its cost.
2. **Source before story.** Each event/news item retains a source URL, source class, observed/published time and affected-asset context. Official sources confirm primary events; media is context.
3. **No fake live data.** A provider failure produces `provider_unavailable`, a null price, or an explicitly marked stale cache—not a made-up value. Market quotes include source and timestamp where returned.
4. **Opportunity ≠ prediction.** DEX activity scores and research-queue priority scores are heuristics for triage. They are not win probabilities, expected returns, or trade recommendations.
5. **Catalyst → expectation → positioning → reaction.** A news headline matters only through a plausible transmission channel and the difference between what happened and what was already priced in.
6. **Education compounds.** Lessons explain macro transmission, liquidity, event surprises, risk sizing, positioning, asymmetry, relative value, data-vintage bias and backtesting. The lesson system is deterministic and costs nothing per question.
7. **Keep the existing database.** Schema additions use `CREATE TABLE IF NOT EXISTS`; the old `data/edge.db` and trade journal are not deleted.

## Included modules

- **Brief:** crypto market context, cross-asset board, next catalysts, latest source-labelled headlines and provider health.
- **Cross-asset board:** BTC, ETH, gold futures, silver futures, WTI crude, US Dollar Index, S&P 500, Nasdaq Composite, VIX and long-duration Treasury ETF proxy.
- **Events:** next 21 days from FinanceCalendar, with impact, consensus/actual/prior when supplied, affected-asset mapping and a plain-language mechanism. Calendar data is not assumed to be complete or infallible.
- **News:** RSS ingestion from Federal Reserve, ECB, Bank of Japan, SEC EDGAR and crypto publishers. News gets a category and affected-asset tags; tags are heuristics, not sentiment or direction calls.
- **Opportunity Radar:** broad DexScreener search sampling, 1h-vs-6h activity acceleration, transaction pace, buy share, pool liquidity, pair age and extension/thin-liquidity warnings.
- **Asymmetry Lab:** scheduled catalyst watchlists, high-activity DEX research candidates, and conditional cross-asset divergence prompts. Each idea includes evidence to verify, invalidation conditions and risks. It deliberately does not fabricate a target or probability.
- **Risk calculator:** size from account equity, risk fraction and stop distance. Explicitly excludes slippage, fees, funding and gap risk.
- **Paper-trade journal:** local SQLite trade entries, closeout, realized PnL and descriptive expectancy.
- **Knowledge library:** concise lessons, recall questions and local progress tracking. No model/API fee.
- **Watchlist and alerts:** local persistent saved ideas and threshold-crossing activity observations.

## Data sources and cost/licensing notes

The product is designed to start with public/free endpoints and caching. Availability, rate limits and terms can change; verify them before commercial distribution.

- **DexScreener public API:** https://docs.dexscreener.com/api/reference — pair search and DEX observations. Some endpoints have documented 60 requests/minute limits. Current search query coverage is a sample, not an exhaustive universe scanner. Avoid hammering it; default background refresh is every 10 minutes.
- **CoinGecko global endpoint:** https://www.coingecko.com/en/api — aggregate crypto market context. Its published Demo plan currently documents 10,000 call credits/month and 100 requests/minute, with attribution requirements; Edge only calls the global endpoint on refresh. Check current plan/terms before redistributing data.
- **FinanceCalendar:** https://www.financecalendar.com/api/ — keyless economic calendar; its documentation says commercial use is permitted with visible attribution/link. The app includes a source link. The API does not include earnings dates, so those require another source if added later.
- **Official Fed calendar:** https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm — primary-source confirmation of FOMC dates, statements and minutes.
- **Official BLS release schedules:** https://www.bls.gov/schedule/ — CPI and employment release calendars.
- **ECB RSS:** https://www.ecb.europa.eu/home/html/rss.pl.html — official press releases, speeches and statistics feeds.
- **SEC EDGAR APIs:** https://www.sec.gov/about/developer-resources and https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data — public submissions/XBRL data. SEC requires a declared User-Agent and fair-access behavior; do not exceed its published 10 requests/second ceiling. The current RSS feed is for latest filings, not a comprehensive event calendar.
- **Yahoo Finance public chart endpoint:** used only as an indicative, best-effort cross-asset reference quote. It is not a documented exchange-grade API or a guarantee of real-time data. It can be blocked, delayed or changed. The UI explicitly labels it indicative; failed symbols stay null. Replace this adapter with a licensed quote provider if reliable live execution-grade data becomes a requirement.
- **LBMA Gold Price:** do not assume the benchmark can be republished for free. LBMA/ICE state that use or redistribution of the benchmark may require a licence. Edge uses indicative gold futures quotes as a best-effort reference, not a republished LBMA benchmark. See https://www.lbma.org.uk/prices-and-data/lbma-gold-price/lbma-gold-price and https://www.theice.com/publicdocs/IBA_LBMA_Gold_Price_Licensing_FAQ.pdf.
- **FRED/ALFRED:** https://fred.stlouisfed.org/docs/api/fred/ — valuable for rates, real yields, credit and historical macro series, but API v1/v2 requests require a registered API key. This release reserves a future adapter; no fake FRED data is shown and no key is required to run Edge.

## Research methodology

### Events that may move multiple markets

The rule-based classifier maps releases into plausible channels, not one-way predictions:

- **Central banks / rates:** expected policy path, real yields, USD, equity discount rates, gold and crypto liquidity.
- **Inflation:** headline and core details, revisions, consensus surprise, wage/services persistence and market-implied rate path.
- **Labor and growth:** demand, wage pressure, recession risk and rates repricing.
- **Energy / supply:** inventories, OPEC/supply disruptions, inflation and cyclical demand.
- **Geopolitics / sanctions:** supply chains, energy, risk hedging, currencies and volatility.
- **Crypto-specific:** ETF/flow developments, regulation, exchange incidents, hacks, stablecoin stress and protocol changes.
- **Corporate filings/earnings:** actual results, guidance, cash flow, dilution and revisions to forward expectations.

A high-impact label means the event may cause volatility; it does not mean the outcome is predictable. The market reaction depends on the surprise versus expectations, revisions, positioning, liquidity and what is already priced in.

### Asymmetry checklist

Before an idea becomes actionable, a human should be able to answer:

1. **Catalyst:** what changes, and when?
2. **Expectation gap:** what does the market appear to expect, and what observable evidence suggests that expectation may be wrong?
3. **Transmission:** why would the catalyst affect this asset or spread?
4. **Confirmation:** what primary source, price/flow/positioning data supports the thesis?
5. **Invalidation:** what evidence makes the thesis wrong, and where is the thesis no longer valid?
6. **Payoff and costs:** plausible upside/downside ranges, spread, fees, slippage, funding, liquidity and exit capacity.
7. **Portfolio fit:** correlated exposures, concentration and maximum loss.
8. **Evaluation:** log the idea before the outcome; measure forward returns across multiple horizons and regimes, with costs and out-of-sample tests.

The current asymmetry module is an **evidence queue**, not a probability model. A future release should add historical event studies, point-in-time data, out-of-sample testing and explicit calibration before describing any score as predictive.

## Architecture

- Flask app and mobile-first single-page UI.
- SQLite at `data/edge.db` with additive tables for provider cache, learning progress, watchlist, snapshots, alerts and worker state.
- Background `worker.py` refreshes public sources every 600 seconds by default. The browser reads the cached data; manual refresh is available.
- Provider work is parallelized; each provider response carries status and errors. External network/provider availability cannot be guaranteed by unit tests.
- No automated trading, exchange keys, wallet signing, or execution endpoints.

## Local setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m unittest -v test_edge_v2
python app.py
```

Open `http://127.0.0.1:5060`. Press **Refresh intelligence** to fetch provider data. A successful app health check does not imply all data providers responded; inspect the Provider Status panel.

## Existing VPS deployment workflow

This package is intended to replace the application files in `/opt/edge-intelligence` while keeping the existing database. **Do not enable the worker until tests pass.** The app supports optional API-token protection via `EDGE_ACCESS_TOKEN`; the browser prompts for the token and stores it on that device. Because your VPS has a public IP, configure a strong token before exposing the dashboard. Keep it out of GitHub and do not share screenshots containing it. The user manually uploads the ZIP contents to the private GitHub repo and commits them; this project is not auto-pushed by this package.

1. In GitHub, upload the contents of the ZIP (not the ZIP itself) to the repository root, uploading every file from this ZIP to the repository root. This flat package renames the test suite to `test_edge_v2.py` and keeps the static asset URLs working through an explicit Flask route. Replace `app.py`, `intelligence.py`, `storage.py`, `index.html`, `requirements.txt`, `worker.py`, and `edge-scanner.service`; add `.env.example`, `README.md`, `edge-icon.svg`, `manifest.webmanifest`, `sw.js`, and `test_edge_v2.py`.
2. Delete the obsolete legacy test files `test_app.py`, `test_engine.py`, and `test_edge.py` from the repository root if present. Also remove obsolete `tests/test_app.py` and `tests/test_engine.py` if they were moved there during the previous attempt. The new test suite is `test_edge_v2.py` in the repository root.
3. Commit the changes to `main`.
4. On the VPS, back up the DB and refresh the working tree. Because previous debugging moved legacy tests into `tests/`, remove obsolete root-level legacy tests before pulling; do **not** remove `data/`.

```bash
cd /opt/edge-intelligence
mkdir -p /root/edge-backups
DB_BACKUP="/root/edge-backups/edge.db.$(date +%Y%m%d-%H%M%S).bak"
if [ -f data/edge.db ]; then cp -a data/edge.db "$DB_BACKUP"; fi
rm -f test_app.py test_engine.py test_edge.py
git fetch origin
git reset --hard origin/main
if [ -f "$DB_BACKUP" ]; then cp -a "$DB_BACKUP" data/edge.db; fi
/opt/edge-intelligence/.venv/bin/pip install -r requirements.txt
/opt/edge-intelligence/.venv/bin/python -m unittest -v test_edge_v2
```

If tests fail, **stop** and do not restart the service or enable the worker. Send the full test output. If tests pass, configure a token once if you have not already done so. This stores it in the systemd override, not in the repository; the command prints it so you can enter it once in your phone browser. Keep it private. Do not repeat this command if you already have a token configured, because it will rotate the token.

```bash
sudo mkdir -p /etc/systemd/system/edge-intelligence.service.d
TOKEN=$(openssl rand -hex 32)
printf '[Service]\nEnvironment="EDGE_ACCESS_TOKEN=%s"\n' "$TOKEN" | sudo tee /etc/systemd/system/edge-intelligence.service.d/edge-security.conf >/dev/null
sudo chmod 600 /etc/systemd/system/edge-intelligence.service.d/edge-security.conf
sudo systemctl daemon-reload
echo "Save this Edge access token privately: $TOKEN"
```

Then restart and verify:

```bash
sudo systemctl restart edge-intelligence
curl -s http://127.0.0.1:5060/health
```

Then enable the refresh worker:

```bash
sudo cp /opt/edge-intelligence/edge-scanner.service /etc/systemd/system/edge-scanner.service
sudo systemctl daemon-reload
sudo systemctl enable --now edge-scanner
sudo systemctl status edge-scanner --no-pager
```

The worker's first refresh can take several seconds. Inspect logs with `sudo journalctl -u edge-scanner -n 100 --no-pager`. Manual refresh is also available from the app. If the existing service name/paths differ from the environment described above, inspect them before running commands.

## Tests and limitations

The test suite checks event classification, RSS parsing, DEX activity scoring, explicit provider-failure handling, education content, cache persistence, risk validation, trade settlement and watchlist behavior without depending on external internet calls. It does not certify that public providers are currently reachable or that a score is profitable.

Known limitations in this release:
- Economic event coverage and source feed availability are not exhaustive; verify major events against official schedules.
- Yahoo public chart data is unofficial/possibly delayed. No intraday gold spot quote or licensed benchmark feed is promised.
- RSS keyword tagging is heuristic and can misclassify context or omit important stories.
- DEX discovery uses a small set of search queries and cannot guarantee discovery of every new pair. The scanner does not yet perform full holder concentration, honeypot or contract-permission audits.
- No historical event-study engine, earnings calendar, options surface, order-book depth engine, COT positioning, official FRED series adapter, Telegram push delivery, or external LLM is included yet. Those should be added only after defining the data source, licensing/cost, and a measurable product use case.
- No score is claimed to predict returns. The forward-outcome measurement layer must be expanded before predictive claims are made.
