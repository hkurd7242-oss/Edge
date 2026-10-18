# Edge Intelligence

Mobile-first, evidence-oriented market research and execution-assistance MVP. It is a **fresh standalone product**, independent of Sylvo.

## Included now
- Responsive mobile web application (PWA-style UI).
- Global crypto market overview and curated crypto scanner via CoinGecko API.
- Transparent heuristic scoring; scores are not probabilities.
- Evidence and counter-evidence research report.
- Position-size calculator for simple linear instruments.
- Paper-trade journal and descriptive performance statistics.
- SQLite persistence, WAL mode, API health check.
- Gunicorn/systemd deployment templates and basic smoke tests.

## Not included / not falsely represented
This initial codebase does not yet have validated live feeds for every asset class, a full order-book/DEX execution model, licensed equity/forex/futures/options data, broker order placement, multi-user authentication, push notifications, or a statistically validated predictive model. These require specific providers, permissions, testing and further adapters. Unknown or stale data must not be treated as a signal.

## Local development
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Open `http://localhost:5060`.

## VPS deployment
See `DEPLOY_TERMlUS.md`. Configure secrets outside Git; do not commit `.env` or database files.

## API
- `GET /health`
- `GET /api/overview`
- `GET /api/opportunities`
- `GET /api/analyze/<asset>`
- `POST /api/risk`
- `GET /api/trades`
- `POST /api/trades`
- `POST /api/trades/<id>/settle`
- `GET /api/performance`

## Safety
Research-only. No live order execution. Market data may be delayed, rate-limited or unavailable. Verify price, liquidity, fees and instrument specifications independently before trading.
