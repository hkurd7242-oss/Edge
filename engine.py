"""Evidence-first market adapters and transparent opportunity heuristics.
No AI-generated numbers. Provider failures are surfaced; demo fallback is labelled.
"""
import os, time, math, statistics
from datetime import datetime, timezone
import requests

CG_BASE = "https://api.coingecko.com/api/v3"
COINS = [
    ("bitcoin", "BTC"), ("ethereum", "ETH"), ("solana", "SOL"),
    ("avalanche-2", "AVAX"), ("binancecoin", "BNB"), ("ripple", "XRP"),
    ("dogecoin", "DOGE"), ("chainlink", "LINK"), ("sui", "SUI")
]
TIMEOUT = 8

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def _cg(path, params=None):
    headers = {}
    key = os.getenv("COINGECKO_API_KEY")
    if key:
        headers["x-cg-demo-api-key"] = key
    r = requests.get(CG_BASE + path, params=params, headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def _fallback_items(error):
    # Explicitly marked demo data; never represented as current market data.
    samples = [
        ("BTC", 65000, 1.4, 1.8), ("ETH", 3200, 0.7, 2.1),
        ("SOL", 145, 4.8, 3.5), ("AVAX", 28, -1.2, 1.1),
        ("BNB", 580, 0.8, 0.9)
    ]
    out = []
    for symbol, price, change, volume in samples:
        out.append({
            "asset": symbol, "name": symbol, "price": price,
            "change_24h_pct": change, "volume_24h_usd": volume*1e9,
            "market_cap_usd": None, "source": "DEMO FALLBACK — NOT LIVE",
            "updated_at": now_iso(), "stage": "Data unavailable",
            "score": None, "reasons": ["Provider request failed; no live conclusion is available."],
            "risks": [str(error)[:180]], "action_state": "unverified"
        })
    return out

def market_overview():
    try:
        data = _cg("/global")
        g = data.get("data", {})
        m = g.get("market_cap_percentage", {})
        return {
            "source": "CoinGecko API",
            "updated_at": now_iso(),
            "total_market_cap_usd": g.get("total_market_cap", {}).get("usd"),
            "total_volume_24h_usd": g.get("total_volume", {}).get("usd"),
            "market_cap_change_24h_pct": g.get("market_cap_change_percentage_24h_usd"),
            "btc_dominance_pct": m.get("btc"),
            "data_status": "live response"
        }
    except Exception as e:
        return {"source": "unavailable", "updated_at": now_iso(), "data_status": "unavailable", "warning": str(e)[:180]}

def scan_crypto():
    try:
        ids = ",".join(c[0] for c in COINS)
        raw = _cg("/coins/markets", {"vs_currency":"usd", "ids":ids, "order":"market_cap_desc",
                                     "per_page":len(COINS), "page":1, "sparkline":"false",
                                     "price_change_percentage":"24h"})
        out = []
        for c in raw:
            price = c.get("current_price")
            change = c.get("price_change_percentage_24h")
            vol = c.get("total_volume") or 0
            cap = c.get("market_cap") or 0
            # Transparent screening heuristic, deliberately not called a probability.
            reasons, risks = [], []
            score = 0
            if change is not None:
                if change > 2:
                    score += 20; reasons.append(f"Positive 24h move: {change:.2f}%.")
                elif change < -5:
                    risks.append(f"Sharp 24h decline: {change:.2f}%.")
                else:
                    reasons.append(f"24h move is {change:.2f}%; momentum is not strongly positive.")
            if cap and vol:
                ratio = vol / cap
                if ratio > .12:
                    score += 20; reasons.append(f"24h volume/market-cap ratio is elevated ({ratio:.1%}).")
                else:
                    reasons.append(f"24h volume/market-cap ratio: {ratio:.1%}.")
                if ratio < .01:
                    risks.append("Low reported volume relative to market capitalization.")
            if c.get("market_cap_rank") and c["market_cap_rank"] <= 20:
                score += 10; reasons.append("Within the top 20 by reported market capitalization.")
            if not risks:
                risks.append("This screen does not measure order-book depth, token concentration, or executable slippage.")
            if score >= 35: stage = "Worth investigating"
            elif score >= 20: stage = "Developing"
            else: stage = "No strong screen"
            out.append({
                "asset": c.get("symbol","").upper(), "name": c.get("name"),
                "price": price, "change_24h_pct": change, "volume_24h_usd": vol,
                "market_cap_usd": cap, "market_cap_rank": c.get("market_cap_rank"),
                "source": "CoinGecko API", "updated_at": now_iso(),
                "stage": stage, "score": score, "reasons": reasons, "risks": risks,
                "action_state": "research_only"
            })
        return out
    except Exception as e:
        return _fallback_items(e)

def analyze_asset(asset):
    asset = asset.upper().replace("USDT","").replace("-USD","").replace("USD","")
    items = scan_crypto()
    found = next((x for x in items if x["asset"] == asset or (x.get("name") or "").upper() == asset), None)
    if not found:
        return {
            "asset": asset, "status": "not_found_in_initial_universe",
            "message": "This initial release only resolves a curated crypto universe. Add a licensed data adapter to support this instrument.",
            "evidence": [], "counter_evidence": ["No validated market data found."],
            "action_state": "unverified", "source": "none"
        }
    return {
        **found,
        "thesis": f"{found['asset']} is surfaced for review based on its current reported market snapshot, not a forecast.",
        "evidence": found["reasons"],
        "counter_evidence": found["risks"],
        "conditions_to_review": ["Confirm price structure on the intended timeframe.", "Verify source freshness and executable liquidity.", "Define invalidation before considering a trade."],
        "invalidation": "No structural invalidation is calculated by this market-snapshot-only MVP.",
        "methodology": "Simple transparent screening heuristic. Not backtested; score is not a probability or recommendation."
    }

def risk_calculation(d):
    equity = float(d.get("equity", 0))
    risk_pct = float(d.get("risk_pct", 0))
    entry = float(d.get("entry", 0))
    stop = float(d.get("stop", 0))
    cost_pct = float(d.get("cost_pct", 0))
    if min(equity, risk_pct, entry, stop) <= 0 or entry == stop or cost_pct < 0:
        raise ValueError("Equity, risk %, entry and stop must be positive; entry and stop must differ; costs cannot be negative.")
    if risk_pct > 100:
        raise ValueError("Risk percentage cannot exceed 100.")
    budget = equity * risk_pct / 100
    distance = abs(entry-stop)
    effective = distance + entry*cost_pct/100
    qty = budget/effective
    return {
        "risk_budget": round(budget, 2), "quantity": round(qty, 8),
        "notional": round(qty*entry, 2), "stop_distance_pct": round(distance/entry*100, 4),
        "estimated_cost_allowance_pct": cost_pct,
        "warning": "Simplified linear-instrument estimate. Gaps, spread, slippage, leverage, funding, borrow costs and liquidation can increase losses."
    }
