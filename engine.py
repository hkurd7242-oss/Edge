"""Evidence-first Edge market screening and asset lookup."""
import os
from datetime import datetime, timezone
import requests

CG_BASE = "https://api.coingecko.com/api/v3"
TIMEOUT = 10
DEFAULT_MARKET_LIMIT = 100
MAX_MARKET_LIMIT = 250

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def _cg(path, params=None):
    headers = {"accept": "application/json"}
    key = os.getenv("COINGECKO_API_KEY")
    if key:
        headers["x-cg-demo-api-key"] = key
    response = requests.get(CG_BASE + path, params=params, headers=headers, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()

def _fallback_items(error):
    samples = [("BTC",65000,1.4,1.8),("ETH",3200,.7,2.1),("SOL",145,4.8,3.5),("AVAX",28,-1.2,1.1),("BNB",580,.8,.9)]
    return [{"asset":s,"name":s,"price":p,"change_24h_pct":ch,"volume_24h_usd":v*1e9,
        "market_cap_usd":None,"source":"DEMO FALLBACK — NOT LIVE","updated_at":now_iso(),
        "stage":"Data unavailable","score":None,
        "reasons":["Provider request failed; no live conclusion is available."],
        "risks":[str(error)[:180]],"action_state":"unverified","data_status":"demo_fallback"}
        for s,p,ch,v in samples]

def market_overview():
    try:
        g = _cg("/global").get("data", {})
        dom = g.get("market_cap_percentage", {})
        return {"source":"CoinGecko API","updated_at":now_iso(),
            "total_market_cap_usd":g.get("total_market_cap",{}).get("usd"),
            "total_volume_24h_usd":g.get("total_volume",{}).get("usd"),
            "market_cap_change_24h_pct":g.get("market_cap_change_percentage_24h_usd"),
            "btc_dominance_pct":dom.get("btc"),"data_status":"live response"}
    except Exception as e:
        return {"source":"unavailable","updated_at":now_iso(),"data_status":"unavailable","warning":str(e)[:180]}

def _market_limit():
    try: value = int(os.getenv("EDGE_MARKET_LIMIT", str(DEFAULT_MARKET_LIMIT)))
    except (TypeError, ValueError): value = DEFAULT_MARKET_LIMIT
    return max(10, min(value, MAX_MARKET_LIMIT))

def _score_market_coin(c):
    change, vol, cap = c.get("price_change_percentage_24h"), c.get("total_volume") or 0, c.get("market_cap") or 0
    reasons, risks, score = [], [], 0
    if change is not None:
        if change > 2:
            score += 20; reasons.append(f"Positive 24h move: {change:.2f}%.")
        elif change < -5: risks.append(f"Sharp 24h decline: {change:.2f}%.")
        else: reasons.append(f"24h move is {change:.2f}%; momentum is not strongly positive.")
    ratio = vol/cap if vol and cap else None
    if ratio is not None:
        if ratio > .12:
            score += 20; reasons.append(f"24h volume/market-cap ratio is elevated ({ratio:.1%}).")
        else: reasons.append(f"24h volume/market-cap ratio: {ratio:.1%}.")
        if ratio < .01: risks.append("Low reported volume relative to market capitalization.")
    rank = c.get("market_cap_rank")
    if rank and rank <= 20:
        score += 10; reasons.append("Within the top 20 by reported market capitalization.")
    if not risks:
        risks.append("This screen does not measure order-book depth, token concentration, contract risk, or executable slippage.")
    stage = "Worth investigating" if score >= 35 else ("Developing" if score >= 20 else "No strong screen")
    return {"asset":(c.get("symbol") or "").upper(),"name":c.get("name"),"coin_id":c.get("id"),
        "image":c.get("image"),"price":c.get("current_price"),"change_24h_pct":change,
        "volume_24h_usd":vol,"market_cap_usd":cap,"market_cap_rank":rank,
        "circulating_supply":c.get("circulating_supply"),"total_supply":c.get("total_supply"),
        "volume_market_cap_ratio":round(ratio,6) if ratio is not None else None,
        "source":"CoinGecko API","updated_at":now_iso(),"stage":stage,"score":score,
        "reasons":reasons,"risks":risks,"action_state":"research_only","data_status":"live_response",
        "methodology":"Transparent snapshot heuristic, not a probability or trade recommendation."}

def scan_crypto():
    """Market-cap-ranked discovery; default 100, maximum 250. Not a new-DEX-pair scanner."""
    try:
        raw = _cg("/coins/markets", {"vs_currency":"usd","order":"market_cap_desc",
            "per_page":_market_limit(),"page":1,"sparkline":"false","price_change_percentage":"24h"})
        return [_score_market_coin(c) for c in raw]
    except Exception as e:
        return _fallback_items(e)

def _resolve_asset(query):
    try:
        coins = _cg("/search", {"query":query}).get("coins") or []
        if not coins: return None, "No matching asset was returned by CoinGecko search."
        q = query.strip().lower()
        exact = next((c for c in coins if str(c.get("id","")).lower()==q or
            str(c.get("symbol","")).lower()==q or str(c.get("name","")).lower()==q), None)
        return exact or coins[0], None
    except Exception as e:
        return None, f"CoinGecko search unavailable: {str(e)[:150]}"

def analyze_asset(asset):
    query = str(asset or "").strip()
    upper = query.upper()
    for suffix in ("USDT","-USD","USD"):
        if upper.endswith(suffix) and len(query)>len(suffix):
            query=query[:-len(suffix)].strip(); break
    if not query:
        return {"asset":"","status":"invalid_asset","message":"Enter an asset symbol, name, or CoinGecko ID.",
            "evidence":[],"counter_evidence":["No asset was supplied."],"action_state":"unverified","source":"none"}
    resolved, error = _resolve_asset(query)
    if not resolved:
        return {"asset":query.upper(),"status":"not_found","message":error or "No matching asset found.",
            "evidence":[],"counter_evidence":["No validated market snapshot is available."],
            "action_state":"unverified","source":"CoinGecko search"}
    coin_id = resolved.get("id")
    try:
        rows = _cg("/coins/markets", {"vs_currency":"usd","ids":coin_id,"sparkline":"false",
            "price_change_percentage":"24h"})
        if not rows: raise ValueError("Search match has no current market snapshot.")
        found = _score_market_coin(rows[0])
    except Exception as e:
        return {"asset":(resolved.get("symbol") or query).upper(),"name":resolved.get("name"),
            "coin_id":coin_id,"status":"market_data_unavailable",
            "message":f"Asset resolved, but current market data is unavailable: {str(e)[:150]}",
            "evidence":[],"counter_evidence":["Do not treat search metadata as current price evidence."],
            "action_state":"unverified","source":"CoinGecko API"}
    return {**found,"status":"ok",
        "thesis":f"{found['asset']} is surfaced for review based on its reported market snapshot, not a forecast.",
        "evidence":found["reasons"],"counter_evidence":found["risks"],
        "conditions_to_review":["Confirm price structure on the intended timeframe.",
            "Verify source freshness and executable liquidity.",
            "Check the correct token contract and chain before considering a trade.",
            "Define invalidation before considering a trade."],
        "invalidation":"No structural invalidation is calculated by this market-snapshot-only screen.",
        "methodology":"Simple transparent screening heuristic. Not backtested; score is not a probability or recommendation."}

def risk_calculation(data):
    equity=float(data.get("equity",0)); risk_pct=float(data.get("risk_pct",0))
    entry=float(data.get("entry",0)); stop=float(data.get("stop",0)); cost_pct=float(data.get("cost_pct",0))
    if min(equity,risk_pct,entry,stop)<=0 or entry==stop or cost_pct<0:
        raise ValueError("Equity, risk %, entry and stop must be positive; entry and stop must differ; costs cannot be negative.")
    if risk_pct>100: raise ValueError("Risk percentage cannot exceed 100.")
    budget=equity*risk_pct/100; distance=abs(entry-stop); effective=distance+entry*cost_pct/100
    qty=budget/effective
    return {"risk_budget":round(budget,2),"quantity":round(qty,8),"notional":round(qty*entry,2),
        "stop_distance_pct":round(distance/entry*100,4),"estimated_cost_allowance_pct":cost_pct,
        "warning":"Simplified linear-instrument estimate. Gaps, spread, slippage, leverage, funding, borrow costs and liquidation can increase losses."}
