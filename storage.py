import sqlite3, json, time, os
from datetime import datetime, timezone

def connect(path):
    c = sqlite3.connect(path, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=8000")
    return c

def init_db(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with connect(path) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS opportunities(
          id INTEGER PRIMARY KEY AUTOINCREMENT, asset TEXT NOT NULL, stage TEXT,
          score REAL, payload TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_opp_asset ON opportunities(asset);
        CREATE TABLE IF NOT EXISTS trades(
          id INTEGER PRIMARY KEY AUTOINCREMENT, asset TEXT NOT NULL, direction TEXT NOT NULL,
          entry REAL NOT NULL, stop REAL NOT NULL, quantity REAL NOT NULL,
          status TEXT NOT NULL DEFAULT 'open', opened_at TEXT NOT NULL,
          closed_at TEXT, exit REAL, pnl REAL, risk_amount REAL NOT NULL, payload TEXT
        );
        """)

def save_opportunity(path, item):
    with connect(path) as c:
        c.execute("INSERT INTO opportunities(asset,stage,score,payload,updated_at) VALUES(?,?,?,?,?)",
                  (item.get("asset","?"), item.get("stage"), item.get("score"), json.dumps(item), item.get("updated_at") or datetime.now(timezone.utc).isoformat()))

def list_opportunities(path, limit=60):
    with connect(path) as c:
        rows = c.execute("SELECT payload FROM opportunities ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    seen, out = set(), []
    for r in rows:
        d = json.loads(r["payload"])
        if d.get("asset") not in seen:
            seen.add(d.get("asset")); out.append(d)
    return out

def save_trade(path, d):
    asset = str(d["asset"]).upper().strip()
    direction = str(d["direction"]).lower()
    entry, stop, qty = float(d["entry"]), float(d["stop"]), float(d["quantity"])
    if not asset or direction not in ("long","short") or min(entry,stop,qty) <= 0:
        raise ValueError("Asset required; direction must be long/short; entry, stop and quantity must be positive.")
    if (direction == "long" and stop >= entry) or (direction == "short" and stop <= entry):
        raise ValueError("Stop must be below entry for long trades and above entry for short trades.")
    risk = abs(entry-stop)*qty
    now = datetime.now(timezone.utc).isoformat()
    with connect(path) as c:
        cur = c.execute("INSERT INTO trades(asset,direction,entry,stop,quantity,status,opened_at,risk_amount,payload) VALUES(?,?,?,?,?,'open',?,?,?)",
                        (asset,direction,entry,stop,qty,now,risk,json.dumps(d)))
        trade_id = cur.lastrowid
    return {"id": trade_id, "asset":asset, "direction":direction, "entry":entry,"stop":stop,"quantity":qty,"risk_amount":risk,"status":"open"}

def list_trades(path):
    with connect(path) as c:
        rows = c.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 500").fetchall()
    return [dict(r) for r in rows]

def settle_trade(path, trade_id, exit_price):
    if exit_price <= 0: raise ValueError("Exit price must be positive.")
    with connect(path) as c:
        row = c.execute("SELECT * FROM trades WHERE id=?", (trade_id,)).fetchone()
        if not row: raise ValueError("Trade not found.")
        if row["status"] != "open": raise ValueError("Trade is already closed.")
        pnl = ((exit_price-row["entry"]) if row["direction"]=="long" else (row["entry"]-exit_price))*row["quantity"]
        c.execute("UPDATE trades SET status='closed', exit=?, pnl=?, closed_at=? WHERE id=?",
                  (exit_price,pnl,datetime.now(timezone.utc).isoformat(),trade_id))
    return {"id":trade_id,"exit":exit_price,"pnl":round(pnl,6),"status":"closed","note":"P&L excludes fees, funding and slippage."}
