import sqlite3, json, os
from datetime import datetime, timezone

def connect(path):
    c=sqlite3.connect(path,timeout=15)
    c.row_factory=sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=10000")
    return c

def init_db(path):
    os.makedirs(os.path.dirname(path) or ".",exist_ok=True)
    with connect(path) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS opportunities(id INTEGER PRIMARY KEY AUTOINCREMENT,asset TEXT NOT NULL,stage TEXT,score REAL,payload TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_opp_asset ON opportunities(asset);
        CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY AUTOINCREMENT,asset TEXT NOT NULL,direction TEXT NOT NULL,entry REAL NOT NULL,stop REAL NOT NULL,quantity REAL NOT NULL,status TEXT NOT NULL DEFAULT 'open',opened_at TEXT NOT NULL,closed_at TEXT,exit REAL,pnl REAL,risk_amount REAL NOT NULL,payload TEXT);
        CREATE TABLE IF NOT EXISTS activity_snapshots(id INTEGER PRIMARY KEY AUTOINCREMENT,pair_key TEXT NOT NULL,chain TEXT,asset TEXT NOT NULL,price REAL,volume_1h REAL,volume_24h REAL,liquidity REAL,transactions_24h INTEGER,score REAL,payload TEXT NOT NULL,observed_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_snap_pair_time ON activity_snapshots(pair_key,id DESC);
        CREATE TABLE IF NOT EXISTS alert_events(id INTEGER PRIMARY KEY AUTOINCREMENT,pair_key TEXT NOT NULL,asset TEXT NOT NULL,event_type TEXT NOT NULL,severity TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_alert_time ON alert_events(id DESC);
        CREATE TABLE IF NOT EXISTS worker_state(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        """)

def save_opportunity(path,item):
    with connect(path) as c:
        c.execute("INSERT INTO opportunities(asset,stage,score,payload,updated_at) VALUES(?,?,?,?,?)",
          (item.get("asset","?"),item.get("stage"),item.get("score"),json.dumps(item),item.get("updated_at") or datetime.now(timezone.utc).isoformat()))

def list_opportunities(path,limit=60):
    with connect(path) as c:
        rows=c.execute("SELECT payload FROM opportunities ORDER BY id DESC LIMIT ?",(max(1,min(int(limit),250)),)).fetchall()
    seen=set(); out=[]
    for r in rows:
        d=json.loads(r["payload"]); key=d.get("pair_address") or (d.get("chain"),d.get("asset"))
        if key in seen: continue
        seen.add(key); out.append(d)
    return out

def save_snapshot(path,item):
    key=str(item.get("chain") or "")+":"+str(item.get("pair_address") or item.get("token_address") or item.get("asset"))
    now=item.get("updated_at") or datetime.now(timezone.utc).isoformat()
    with connect(path) as c:
        prev=c.execute("SELECT * FROM activity_snapshots WHERE pair_key=? ORDER BY id DESC LIMIT 1",(key,)).fetchone()
        c.execute("INSERT INTO activity_snapshots(pair_key,chain,asset,price,volume_1h,volume_24h,liquidity,transactions_24h,score,payload,observed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
          (key,item.get("chain"),item.get("asset"),item.get("price"),item.get("volume_1h_usd"),item.get("volume_24h_usd"),item.get("liquidity_usd"),item.get("transactions_24h"),item.get("score"),json.dumps(item),now))
        event=None
        if prev:
            old=json.loads(prev["payload"]); oldscore=float(old.get("score") or 0); newscore=float(item.get("score") or 0)
            oldvol=float(old.get("volume_1h_usd") or 0); newvol=float(item.get("volume_1h_usd") or 0)
            if newscore>=35 and oldscore<35:
                event=("score_cross","high","Screen score crossed into high-activity tier.")
            elif oldvol>0 and newvol>=oldvol*2.5:
                event=("volume_acceleration","medium",f"Reported 1h volume rose {newvol/oldvol:.1f}× between observations.")
        if event:
            c.execute("INSERT INTO alert_events(pair_key,asset,event_type,severity,payload,created_at) VALUES(?,?,?,?,?,?)",
              (key,item.get("asset","?"),event[0],event[1],json.dumps({"message":event[2],"item":item}),now))
    return {"pair_key":key,"alert":event}

def latest_alerts(path,limit=50):
    with connect(path) as c:
        rows=c.execute("SELECT * FROM alert_events ORDER BY id DESC LIMIT ?",(max(1,min(int(limit),200)),)).fetchall()
    return [{"id":r["id"],"asset":r["asset"],"event_type":r["event_type"],"severity":r["severity"],
        **json.loads(r["payload"]),"created_at":r["created_at"]} for r in rows]

def worker_status(path):
    with connect(path) as c:
        rows=c.execute("SELECT key,value FROM worker_state").fetchall()
    return {r["key"]:r["value"] for r in rows}

def set_worker_state(path,key,value):
    with connect(path) as c:
        c.execute("INSERT INTO worker_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,str(value)))

def save_trade(path,d):
    asset=str(d["asset"]).upper().strip(); direction=str(d["direction"]).lower()
    entry,stop,qty=float(d["entry"]),float(d["stop"]),float(d["quantity"])
    if not asset or direction not in ("long","short") or min(entry,stop,qty)<=0:
        raise ValueError("Asset required; direction must be long/short; entry, stop and quantity must be positive.")
    if (direction=="long" and stop>=entry) or (direction=="short" and stop<=entry):
        raise ValueError("Stop must be below entry for long trades and above entry for short trades.")
    risk=abs(entry-stop)*qty; now=datetime.now(timezone.utc).isoformat()
    with connect(path) as c:
        cur=c.execute("INSERT INTO trades(asset,direction,entry,stop,quantity,status,opened_at,risk_amount,payload) VALUES(?,?,?,?,?,'open',?,?,?)",
          (asset,direction,entry,stop,qty,now,risk,json.dumps(d)))
    return {"id":cur.lastrowid,"asset":asset,"direction":direction,"entry":entry,"stop":stop,"quantity":qty,"risk_amount":risk,"status":"open"}

def list_trades(path):
    with connect(path) as c: rows=c.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 500").fetchall()
    return [dict(r) for r in rows]

def settle_trade(path,trade_id,exit_price):
    if exit_price<=0: raise ValueError("Exit price must be positive.")
    with connect(path) as c:
        row=c.execute("SELECT * FROM trades WHERE id=?",(trade_id,)).fetchone()
        if not row: raise ValueError("Trade not found.")
        if row["status"]!="open": raise ValueError("Trade is already closed.")
        pnl=((exit_price-row["entry"]) if row["direction"]=="long" else (row["entry"]-exit_price))*row["quantity"]
        c.execute("UPDATE trades SET status='closed',exit=?,pnl=?,closed_at=? WHERE id=?",(exit_price,pnl,datetime.now(timezone.utc).isoformat(),trade_id))
    return {"id":trade_id,"exit":exit_price,"pnl":round(pnl,6),"status":"closed","note":"P&L excludes fees, funding and slippage."}
