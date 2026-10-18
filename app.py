import os, json, sqlite3, time, math
from datetime import datetime, timezone
from flask import Flask, jsonify, request, render_template_string
from engine import scan_crypto, analyze_asset, risk_calculation, market_overview
from storage import init_db, save_opportunity, list_opportunities, save_trade, list_trades, settle_trade

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("EDGE_DB_PATH", os.path.join(APP_DIR, "data", "edge.db"))
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False
init_db(DB_PATH)

HTML = open(os.path.join(APP_DIR, "index.html"), encoding="utf-8").read()

@app.get("/")
def home():
    return render_template_string(HTML)

@app.get("/health")
def health():
    return jsonify({"ok": True, "app": "Edge Intelligence", "time": datetime.now(timezone.utc).isoformat()})

@app.get("/api/overview")
def overview():
    return jsonify(market_overview())

@app.get("/api/opportunities")
def opportunities():
    refresh = request.args.get("refresh", "0") == "1"
    items = scan_crypto()
    for item in items:
        save_opportunity(DB_PATH, item)
    stored = list_opportunities(DB_PATH, limit=60)
    return jsonify({"items": stored, "refreshed": refresh, "source_note": "Market snapshots are provider-dependent; each item reports its source and freshness."})

@app.get("/api/analyze/<path:asset>")
def analyze(asset):
    return jsonify(analyze_asset(asset.upper()))

@app.post("/api/risk")
def risk():
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(risk_calculation(data))
    except (ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400

@app.get("/api/trades")
def trades():
    return jsonify({"items": list_trades(DB_PATH)})

@app.post("/api/trades")
def add_trade():
    data = request.get_json(silent=True) or {}
    required = ["asset", "direction", "entry", "stop", "quantity"]
    if any(k not in data for k in required):
        return jsonify({"error": "Required fields: asset, direction, entry, stop, quantity"}), 400
    try:
        result = save_trade(DB_PATH, data)
        return jsonify(result), 201
    except (ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400

@app.post("/api/trades/<int:trade_id>/settle")
def close_trade(trade_id):
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(settle_trade(DB_PATH, trade_id, float(data["exit"])))
    except (KeyError, ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400

@app.get("/api/performance")
def performance():
    trades = list_trades(DB_PATH)
    closed = [t for t in trades if t["status"] == "closed"]
    wins = [t for t in closed if (t.get("pnl") or 0) > 0]
    pnl = sum(t.get("pnl") or 0 for t in closed)
    risk_units = [t["risk_amount"] for t in closed if t.get("risk_amount", 0) > 0]
    r_values = [(t.get("pnl") or 0) / t["risk_amount"] for t in closed if t.get("risk_amount", 0) > 0]
    return jsonify({
        "closed_trades": len(closed),
        "win_rate_pct": round(100*len(wins)/len(closed), 2) if closed else None,
        "realized_pnl": round(pnl, 4),
        "expectancy_r": round(sum(r_values)/len(r_values), 3) if r_values else None,
        "sample_warning": "Statistics are descriptive, not predictive. Interpret only with a meaningful sample and complete fees/slippage."
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5060")), debug=False)
