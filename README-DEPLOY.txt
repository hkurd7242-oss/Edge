EDGE SCANNER UPGRADE — DEPLOYMENT NOTES

Files:
- engine.py: replace the current engine.py
- tests/test_engine.py: add this test file (create tests/ if needed)

Changes:
- Broadens the fixed nine-coin list to a CoinGecko market-cap-ranked universe.
- Default 100 assets; EDGE_MARKET_LIMIT can be configured from 10 to 250.
- Analysis can resolve symbols, names, or CoinGecko IDs using provider search.
- Adds coin ID, logo URL, supply metadata, volume/cap ratio and data-status metadata.
- Keeps scoring transparent; score is not a probability or recommendation.
- Provider failures are marked unverified/demo, not live market data.

Limits:
This does not discover every newly launched DEX pair. That requires a separate DEX data adapter. The existing UI may not display every new metadata field until its rendering is updated. Existing storage.py and the SQLite database are untouched.

Deploy:
1. Back up engine.py.
2. Replace engine.py and add tests/test_engine.py in GitHub; commit.
3. On VPS:
   cd /opt/edge-intelligence
   git pull
   /opt/edge-intelligence/.venv/bin/python -m unittest discover -s tests -v
   sudo systemctl restart edge-intelligence
   sudo systemctl status edge-intelligence --no-pager
   curl -fsS http://127.0.0.1:5060/health
   curl -fsS http://127.0.0.1:5060/api/opportunities | head -c 1000

Rollback: restore the backed-up engine.py, commit the revert, git pull, restart service.
