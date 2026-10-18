import os, json, time
from datetime import datetime, timezone
from flask import Flask, jsonify, request, render_template_string
from engine import scan_opportunities, analyze_asset, risk_calculation, market_overview
from storage import init_db, save_opportunity, list_opportunities, save_trade, list_trades, settle_trade, save_snapshot, latest_alerts, worker_status

APP_DIR=os.path.dirname(os.path.abspath(__file__))
DB_PATH=os.environ.get("EDGE_DB_PATH",os.path.join(APP_DIR,"data","edge.db"))
os.makedirs(os.path.dirname(DB_PATH),exist_ok=True)
app=Flask(__name__); app.config["JSON_SORT_KEYS"]=False
init_db(DB_PATH)
with open(os.path.join(APP_DIR,"index.html"),encoding="utf-8") as f: HTML=f.read()

def ingest():
    result=scan_opportunities()
    for item in result.get("items",[]):
        save_opportunity(DB_PATH,item); save_snapshot(DB_PATH,item)
    return result

@app.get("/")
def home(): return render_template_string(HTML)

@app.get("/health")
def health():
    state=worker_status(DB_PATH)
    return jsonify({"ok":True,"app":"Edge Opportunity Intelligence","time":datetime.now(timezone.utc).isoformat(),"worker":state.get("last_success","not_seen")})

@app.get("/api/overview")
def overview(): return jsonify(market_overview())

@app.get("/api/opportunities")
def opportunities():
    refresh=request.args.get("refresh","0")=="1"
    result=ingest() if refresh else None
    stored=list_opportunities(DB_PATH,limit=120)
    if not stored and not refresh: result=ingest(); stored=list_opportunities(DB_PATH,limit=120)
    return jsonify({"items":stored,"refreshed":bool(refresh),"data_status":(result or {}).get("data_status","cached"),
        "updated_at":(result or {}).get("updated_at"),"discovered_pairs":(result or {}).get("discovered_pairs"),
        "provider_errors":(result or {}).get("provider_errors",[]),"worker":worker_status(DB_PATH),
        "source_note":"DEX pair observations are not guarantees of token safety, liquidity quality or profitability."})

@app.get("/api/analyze/<path:asset>")
def analyze(asset): return jsonify(analyze_asset(asset))

@app.get("/api/alerts")
def alerts(): return jsonify({"items":latest_alerts(DB_PATH),"worker":worker_status(DB_PATH)})

@app.get("/api/worker")
def worker(): return jsonify(worker_status(DB_PATH))

@app.post("/api/risk")
def risk():
    try: return jsonify(risk_calculation(request.get_json(silent=True) or {}))
    except (ValueError,TypeError) as e: return jsonify({"error":str(e)}),400

@app.get("/api/trades")
def trades(): return jsonify({"items":list_trades(DB_PATH)})

@app.post("/api/trades")
def add_trade():
    data=request.get_json(silent=True) or {}
    if any(k not in data for k in ("asset","direction","entry","stop","quantity")):
        return jsonify({"error":"Required fields: asset, direction, entry, stop, quantity"}),400
    try: return jsonify(save_trade(DB_PATH,data)),201
    except (ValueError,TypeError) as e: return jsonify({"error":str(e)}),400

@app.post("/api/trades/<int:trade_id>/settle")
def close_trade(trade_id):
    try: return jsonify(settle_trade(DB_PATH,trade_id,float((request.get_json(silent=True) or {})["exit"])))
    except (KeyError,ValueError,TypeError) as e: return jsonify({"error":str(e)}),400

@app.get("/api/performance")
def performance():
    closed=[t for t in list_trades(DB_PATH) if t["status"]=="closed"]
    wins=[t for t in closed if (t.get("pnl") or 0)>0]
    pnl=sum(t.get("pnl") or 0 for t in closed)
    rs=[(t.get("pnl") or 0)/t["risk_amount"] for t in closed if t.get("risk_amount",0)>0]
    return jsonify({"closed_trades":len(closed),"win_rate_pct":round(100*len(wins)/len(closed),2) if closed else None,
      "realized_pnl":round(pnl,4),"expectancy_r":round(sum(rs)/len(rs),3) if rs else None,
      "sample_warning":"Descriptive only; excludes fees, funding and slippage."})

if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT","5060")),debug=False)
