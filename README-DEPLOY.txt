EDGE OPPORTUNITY INTELLIGENCE — FULL REBUILD PACKAGE

Replace these tracked files in the existing repository:
- app.py
- engine.py
- storage.py
- index.html (full UI redesign)
- requirements.txt

Add:
- worker.py
- edge-scanner.service (systemd unit template; install separately)
- tests/test_edge.py

PRODUCT CHANGES
- Discovery uses DexScreener search results across configurable search terms instead of a static nine-coin CoinGecko universe.
- Opportunity ranking uses reported 1h/6h/24h volume, transaction pace, buys/sells, liquidity, pair age and price movement.
- Research resolves DEX pairs by symbol/name/contract query and reports chain, DEX, pair URL, activity evidence and risks.
- SQLite keeps existing opportunities and trades tables and adds snapshots, alert events, worker state using CREATE TABLE IF NOT EXISTS. Existing DB is not deleted.
- Separate worker polls every 180 seconds by default, persists observations and emits alert events when a pair crosses a score tier or reported 1h volume accelerates sharply.
- Existing paper-trade journal, risk calculator, performance API remain available.
- UI is redesigned around activity signals, chain/pair metadata, evidence, alerts, risk and performance.

IMPORTANT LIMITS
- DexScreener search coverage depends on provider search semantics and API limits. The default search terms are configurable through EDGE_DISCOVERY_QUERIES (semicolon-separated). This is not guaranteed exhaustive cross-chain coverage.
- Pair-level DEX metrics do not establish holder concentration, contract safety, wash trading or real execution price. Contract/holder risk requires chain-specific sources and is not claimed as complete in this build.
- Alerting currently stores events in SQLite and displays them in the app; it does not send Telegram/push notifications.
- Activity acceleration requires multiple worker observations over time. Initial scan has no historical baseline.
- No live trades are executed.

DEPLOY SAFELY
1. Back up current files and database:
   cd /opt/edge-intelligence
   mkdir -p /root/edge-backup-$(date +%Y%m%d-%H%M%S)
   cp app.py engine.py storage.py index.html requirements.txt /root/edge-backup-*/ 2>/dev/null || true
   cp data/edge.db /root/edge-backup-*/edge.db 2>/dev/null || true
   (Better: use one explicitly named backup directory if wildcard is ambiguous.)
2. Commit replacements/additions to main in GitHub.
3. Pull and test:
   cd /opt/edge-intelligence
   git pull origin main
   /opt/edge-intelligence/.venv/bin/pip install -r requirements.txt
   /opt/edge-intelligence/.venv/bin/python -m unittest discover -s tests -v
   sudo systemctl restart edge-intelligence
   curl -fsS http://127.0.0.1:5060/health
   curl -fsS http://127.0.0.1:5060/api/opportunities | head -c 1500

INSTALL BACKGROUND SCANNER
   sudo cp edge-scanner.service /etc/systemd/system/edge-scanner.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now edge-scanner
   sudo systemctl status edge-scanner --no-pager
   journalctl -u edge-scanner -n 50 --no-pager

OPTIONAL ENVIRONMENT
Set EDGE_DISCOVERY_QUERIES as a semicolon-separated list of search terms in both app and worker environments if needed. Set EDGE_SCAN_INTERVAL_SECONDS (minimum 60) for worker cadence. Keep API secrets out of the repository.

ROLLBACK
Restore previous app.py, engine.py, storage.py, index.html, requirements.txt and restart edge-intelligence. Disable scanner with:
   sudo systemctl disable --now edge-scanner
The additive DB tables can remain; they do not replace existing trades or opportunities.
