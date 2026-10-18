"""SQLite persistence. Existing trades/opportunities tables are preserved via additive migrations."""
import sqlite3, json, os
from datetime import datetime, timezone

def connect(path):
    c=sqlite3.connect(path,timeout=20)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA busy_timeout=15000')
    return c

def now(): return datetime.now(timezone.utc).isoformat()

def init_db(path):
    os.makedirs(os.path.dirname(path) or '.',exist_ok=True)
    with connect(path) as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS opportunities(id INTEGER PRIMARY KEY AUTOINCREMENT,asset TEXT NOT NULL,stage TEXT,score REAL,payload TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_opp_asset ON opportunities(asset);
        CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY AUTOINCREMENT,asset TEXT NOT NULL,direction TEXT NOT NULL,entry REAL NOT NULL,stop REAL NOT NULL,quantity REAL NOT NULL,status TEXT NOT NULL DEFAULT 'open',opened_at TEXT NOT NULL,closed_at TEXT,exit REAL,pnl REAL,risk_amount REAL NOT NULL,payload TEXT);
        CREATE TABLE IF NOT EXISTS activity_snapshots(id INTEGER PRIMARY KEY AUTOINCREMENT,pair_key TEXT NOT NULL,chain TEXT,asset TEXT NOT NULL,price REAL,volume_1h REAL,volume_24h REAL,liquidity REAL,transactions_24h INTEGER,score REAL,payload TEXT NOT NULL,observed_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_snap_pair_time ON activity_snapshots(pair_key,id DESC);
        CREATE TABLE IF NOT EXISTS alert_events(id INTEGER PRIMARY KEY AUTOINCREMENT,pair_key TEXT NOT NULL,asset TEXT NOT NULL,event_type TEXT NOT NULL,severity TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_alert_time ON alert_events(id DESC);
        CREATE TABLE IF NOT EXISTS worker_state(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS edge_cache(cache_key TEXT PRIMARY KEY,payload TEXT NOT NULL,updated_at TEXT NOT NULL,status TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS learning_progress(lesson_id TEXT PRIMARY KEY,completed_at TEXT,quiz_correct INTEGER NOT NULL DEFAULT 0,quiz_attempts INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS watchlist(id INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT NOT NULL,identifier TEXT NOT NULL,label TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(kind,identifier));
        ''')

def cache_put(path,key,payload,status='unknown'):
    with connect(path) as c:
        c.execute('INSERT INTO edge_cache(cache_key,payload,updated_at,status) VALUES(?,?,?,?) ON CONFLICT(cache_key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at,status=excluded.status',(key,json.dumps(payload,ensure_ascii=False),now(),status))

def cache_get(path,key,max_age_seconds=None):
    with connect(path) as c: row=c.execute('SELECT * FROM edge_cache WHERE cache_key=?',(key,)).fetchone()
    if not row: return None
    try: age=(datetime.now(timezone.utc)-datetime.fromisoformat(row['updated_at'])).total_seconds()
    except Exception: age=1e12
    if max_age_seconds is not None and age>max_age_seconds: return None
    try: d=json.loads(row['payload'])
    except Exception: return None
    d['_cache']={'updated_at':row['updated_at'],'age_seconds':max(0,int(age)),'status':row['status']}
    return d

def set_state(path,key,value):
    with connect(path) as c: c.execute('INSERT INTO worker_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,str(value)))
def get_state(path):
    with connect(path) as c: rows=c.execute('SELECT key,value FROM worker_state').fetchall()
    return {r['key']:r['value'] for r in rows}

def save_opportunities(path,items):
    with connect(path) as c:
        for item in items:
            c.execute('INSERT INTO opportunities(asset,stage,score,payload,updated_at) VALUES(?,?,?,?,?)',(item.get('asset','?'),item.get('stage'),item.get('score'),json.dumps(item),item.get('updated_at') or now()))

def list_opportunities(path,limit=100):
    with connect(path) as c: rows=c.execute('SELECT payload FROM opportunities ORDER BY id DESC LIMIT ?',(max(1,min(int(limit),250)),)).fetchall()
    seen=set(); out=[]
    for r in rows:
        try: d=json.loads(r['payload'])
        except Exception: continue
        key=d.get('pair_address') or (d.get('chain'),d.get('asset'))
        if key in seen: continue
        seen.add(key); out.append(d)
    return out

def save_snapshot(path,item):
    key=str(item.get('chain') or '')+':'+str(item.get('pair_address') or item.get('token_address') or item.get('asset'))
    with connect(path) as c:
        prev=c.execute('SELECT * FROM activity_snapshots WHERE pair_key=? ORDER BY id DESC LIMIT 1',(key,)).fetchone()
        c.execute('INSERT INTO activity_snapshots(pair_key,chain,asset,price,volume_1h,volume_24h,liquidity,transactions_24h,score,payload,observed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(key,item.get('chain'),item.get('asset'),item.get('price_usd'),item.get('volume_1h_usd'),item.get('volume_24h_usd'),item.get('liquidity_usd'),item.get('transactions_24h'),item.get('score'),json.dumps(item),item.get('updated_at') or now()))
        event=None
        if prev:
            old=json.loads(prev['payload']); oldscore=float(old.get('score') or 0); newscore=float(item.get('score') or 0); oldvol=float(old.get('volume_1h_usd') or 0); newvol=float(item.get('volume_1h_usd') or 0)
            if newscore>=35 and oldscore<35: event=('score_cross','high','Activity screen crossed 35; heuristic only.')
            elif oldvol>0 and newvol>=oldvol*2.5: event=('volume_acceleration','medium',f'Reported 1h volume rose {newvol/oldvol:.1f}× between observations.')
        if event:
            payload={'message':event[2],'pair_url':item.get('pair_url'),'score':item.get('score'),'liquidity_usd':item.get('liquidity_usd')}
            c.execute('INSERT INTO alert_events(pair_key,asset,event_type,severity,payload,created_at) VALUES(?,?,?,?,?,?)',(key,item.get('asset','?'),event[0],event[1],json.dumps(payload),now()))

def latest_alerts(path,limit=60):
    with connect(path) as c: rows=c.execute('SELECT * FROM alert_events ORDER BY id DESC LIMIT ?',(limit,)).fetchall()
    out=[]
    for r in rows:
        d=dict(r); d['payload']=json.loads(d['payload']); out.append(d)
    return out

def save_trade(path,data):
    asset=str(data['asset']).strip(); direction=str(data['direction']).lower(); entry=float(data['entry']); stop=float(data['stop']); qty=float(data['quantity'])
    if not asset or direction not in ('long','short') or min(entry,stop,qty)<=0: raise ValueError('Asset, positive entry/stop/quantity and direction long/short are required.')
    if direction=='long' and stop>=entry: raise ValueError('For a long, stop must be below entry.')
    if direction=='short' and stop<=entry: raise ValueError('For a short, stop must be above entry.')
    risk=abs(entry-stop)*qty
    with connect(path) as c:
        cur=c.execute('INSERT INTO trades(asset,direction,entry,stop,quantity,status,opened_at,risk_amount,payload) VALUES(?,?,?,?,?,?,?,?,?)',(asset,direction,entry,stop,qty,'open',now(),risk,json.dumps(data)))
        tid=cur.lastrowid
    return {'id':tid,'asset':asset,'direction':direction,'entry':entry,'stop':stop,'quantity':qty,'risk_amount':risk,'status':'open','opened_at':now()}

def list_trades(path):
    with connect(path) as c: rows=c.execute('SELECT * FROM trades ORDER BY id DESC LIMIT 300').fetchall()
    return [dict(r) for r in rows]

def settle_trade(path,trade_id,exit_price):
    if exit_price<=0: raise ValueError('Exit price must be positive.')
    with connect(path) as c:
        row=c.execute('SELECT * FROM trades WHERE id=?',(trade_id,)).fetchone()
        if not row: raise ValueError('Trade not found.')
        if row['status']=='closed': raise ValueError('Trade is already closed.')
        pnl=(exit_price-row['entry'])*row['quantity']*(1 if row['direction']=='long' else -1)
        c.execute('UPDATE trades SET status="closed",closed_at=?,exit=?,pnl=? WHERE id=?',(now(),exit_price,pnl,trade_id))
    return {'id':trade_id,'exit':exit_price,'pnl':pnl,'status':'closed'}

def performance(path):
    closed=[t for t in list_trades(path) if t['status']=='closed']; wins=[t for t in closed if (t.get('pnl') or 0)>0]
    rs=[(t.get('pnl') or 0)/t['risk_amount'] for t in closed if (t.get('risk_amount') or 0)>0]
    return {'closed_trades':len(closed),'win_rate_pct':round(100*len(wins)/len(closed),2) if closed else None,'realized_pnl':round(sum(t.get('pnl') or 0 for t in closed),4),'expectancy_r':round(sum(rs)/len(rs),3) if rs else None,'sample_warning':'Descriptive only; excludes fees, funding, slippage and taxes.'}

def save_lesson_result(path,lesson_id,correct):
    with connect(path) as c:
        c.execute('INSERT INTO learning_progress(lesson_id,completed_at,quiz_correct,quiz_attempts) VALUES(?,?,?,1) ON CONFLICT(lesson_id) DO UPDATE SET completed_at=excluded.completed_at,quiz_correct=learning_progress.quiz_correct+excluded.quiz_correct,quiz_attempts=learning_progress.quiz_attempts+1',(lesson_id,now() if correct else None,1 if correct else 0))

def learning_progress(path):
    with connect(path) as c: rows=c.execute('SELECT * FROM learning_progress').fetchall()
    return [dict(r) for r in rows]

def add_watch(path,kind,identifier,label):
    with connect(path) as c:
        c.execute('INSERT OR IGNORE INTO watchlist(kind,identifier,label,created_at) VALUES(?,?,?,?)',(kind,identifier,label,now()))
        row=c.execute('SELECT * FROM watchlist WHERE kind=? AND identifier=?',(kind,identifier)).fetchone()
    return dict(row)
def list_watch(path):
    with connect(path) as c: rows=c.execute('SELECT * FROM watchlist ORDER BY id DESC').fetchall()
    return [dict(r) for r in rows]
def delete_watch(path,watch_id):
    with connect(path) as c: cur=c.execute('DELETE FROM watchlist WHERE id=?',(watch_id,))
    return cur.rowcount>0
