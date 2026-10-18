"""Edge opportunity intelligence: pair discovery, activity signals, and asset research.

Data providers: DexScreener public API for DEX pair discovery and CoinGecko for
global market context. Signals are explainable research screens, not predictions.
"""
import os, time
from datetime import datetime, timezone
import requests

CG_BASE="https://api.coingecko.com/api/v3"
DEX_BASE="https://api.dexscreener.com"
TIMEOUT=12
DEFAULT_LIMIT=max(20,min(250,int(os.getenv("EDGE_MARKET_LIMIT","100")))) if os.getenv("EDGE_MARKET_LIMIT","100").isdigit() else 100
DISCOVERY_QUERIES=[x.strip() for x in os.getenv("EDGE_DISCOVERY_QUERIES","solana;base;ethereum;bnb;avalanche;new pair").split(";") if x.strip()]

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def _get(url, params=None, headers=None):
    r=requests.get(url,params=params,headers=headers or {"accept":"application/json"},timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def _cg(path,params=None):
    h={"accept":"application/json"}
    key=os.getenv("COINGECKO_API_KEY")
    if key: h["x-cg-demo-api-key"]=key
    return _get(CG_BASE+path,params,h)

def _num(v):
    try:
        x=float(v)
        return x if x==x and abs(x)!=float("inf") else None
    except (TypeError,ValueError): return None

def _dex_search(q):
    data=_get(DEX_BASE+"/latest/dex/search",{"q":q})
    return data.get("pairs") or []

def _pair_to_candidate(p):
    base=p.get("baseToken") or {}; quote=p.get("quoteToken") or {}
    tx=p.get("txns") or {}; h1=tx.get("h1") or {}; h6=tx.get("h6") or {}; h24=tx.get("h24") or {}
    vol=p.get("volume") or {}; ch=p.get("priceChange") or {}; liq=p.get("liquidity") or {}
    buys24=_num(h24.get("buys")) or 0; sells24=_num(h24.get("sells")) or 0
    tx24=buys24+sells24
    buys1=_num(h1.get("buys")) or 0; sells1=_num(h1.get("sells")) or 0
    tx1=buys1+sells1
    volume24=_num(vol.get("h24")) or 0; volume6=_num(vol.get("h6")) or 0; volume1=_num(vol.get("h1")) or 0
    liquidity=_num(liq.get("usd")) or 0
    price=_num(p.get("priceUsd"))
    change24=_num(ch.get("h24")); change1=_num(ch.get("h1")); change6=_num(ch.get("h6"))
    created=_num(p.get("pairCreatedAt"))
    age_hours=max(0,(time.time()*1000-created)/3600000) if created else None
    buy_ratio=buys24/tx24 if tx24 else None
    volume_liquidity=volume24/liquidity if liquidity>0 else None
    score=0; evidence=[]; risks=[]
    # Activity acceleration compares adjacent reported windows where possible.
    if volume1>0 and volume6>0:
        baseline=volume6/6
        accel=volume1/baseline if baseline>0 else None
    else: accel=None
    if accel is not None:
        if accel>=2.5: score+=22; evidence.append(f"1h volume is {accel:.1f}× the 6h hourly average.")
        elif accel>=1.5: score+=12; evidence.append(f"1h volume is {accel:.1f}× the 6h hourly average.")
        else: evidence.append(f"1h volume is {accel:.1f}× the 6h hourly average; no strong acceleration.")
    if tx1>0 and tx24>0:
        tx_accel=tx1/(tx24/24)
        if tx_accel>=2.5: score+=15; evidence.append(f"1h transaction pace is {tx_accel:.1f}× the 24h hourly average.")
    if buy_ratio is not None:
        if buy_ratio>=.62 and tx24>=20: score+=10; evidence.append(f"Buys are {buy_ratio:.0%} of reported 24h transactions.")
        elif buy_ratio<.42 and tx24>=20: risks.append(f"Sell-heavy reported flow: buys are only {buy_ratio:.0%} of 24h transactions.")
    if liquidity>=100000: score+=10; evidence.append(f"Reported pool liquidity is ${liquidity:,.0f}.")
    elif liquidity<15000: risks.append(f"Thin reported liquidity (${liquidity:,.0f}); execution impact may be severe.")
    if age_hours is not None and age_hours<72: score+=8; evidence.append(f"Pair age is about {age_hours:.1f} hours.")
    if change24 is not None and change24>15: risks.append(f"Already extended: reported 24h price change is +{change24:.1f}%.")
    if change24 is not None and change24<-20: risks.append(f"Large 24h drawdown: {change24:.1f}%.")
    if volume_liquidity is not None and volume_liquidity>10: risks.append(f"24h volume/liquidity is {volume_liquidity:.1f}×; verify wash-trading risk.")
    if tx24<10: risks.append("Very few reported 24h transactions; activity evidence is weak.")
    if not evidence: evidence.append("Insufficient activity evidence for a strong screen.")
    if not risks: risks.append("DEX pair data does not prove holder distribution, contract safety, or executable liquidity.")
    stage="High activity shift" if score>=45 else "Activity developing" if score>=25 else "Watch"
    return {
      "asset":str(base.get("symbol") or "UNKNOWN").upper(),"name":base.get("name") or base.get("symbol") or "Unknown token",
      "token_address":base.get("address"),"pair_address":p.get("pairAddress"),"chain":p.get("chainId"),
      "dex":p.get("dexId"),"pair_url":p.get("url"),"image":(p.get("info") or {}).get("imageUrl"),
      "quote_symbol":quote.get("symbol"),"price":price,"change_1h_pct":change1,"change_6h_pct":change6,
      "change_24h_pct":change24,"volume_1h_usd":volume1,"volume_6h_usd":volume6,"volume_24h_usd":volume24,
      "liquidity_usd":liquidity,"buys_24h":int(buys24),"sells_24h":int(sells24),"transactions_24h":int(tx24),
      "buy_ratio_24h":round(buy_ratio,4) if buy_ratio is not None else None,
      "volume_liquidity_ratio":round(volume_liquidity,3) if volume_liquidity is not None else None,
      "activity_acceleration":round(accel,2) if accel is not None else None,
      "pair_age_hours":round(age_hours,1) if age_hours is not None else None,
      "market_cap_usd":_num(p.get("marketCap")) or _num(p.get("fdv")),
      "score":score,"stage":stage,"reasons":evidence,"risks":risks,
      "source":"DexScreener API","updated_at":now_iso(),"data_status":"live_response",
      "action_state":"research_only","methodology":"Explainable activity screen using reported DEX pair data; score is not a probability or buy recommendation."
    }

def scan_opportunities(limit=None):
    limit=max(20,min(int(limit or DEFAULT_LIMIT),250))
    pairs=[]; errors=[]
    # Query several ecosystems and trending search terms; deduplicate by chain/pair address.
    queries=DISCOVERY_QUERIES
    for q in queries:
        try: pairs.extend(_dex_search(q))
        except Exception as e: errors.append(f"{q}: {str(e)[:100]}")
    seen=set(); candidates=[]
    for p in pairs:
        key=(str(p.get("chainId","")).lower(),str(p.get("pairAddress","")).lower())
        if not key[1] or key in seen: continue
        seen.add(key)
        try:
            c=_pair_to_candidate(p)
            if c["price"] is None: continue
            candidates.append(c)
        except Exception:
            continue
    candidates.sort(key=lambda x:(x.get("score",0),x.get("volume_1h_usd") or 0,x.get("liquidity_usd") or 0),reverse=True)
    if not candidates and errors:
        return {"items":[],"source":"DexScreener API","updated_at":now_iso(),"data_status":"unavailable","errors":errors[:4],
          "message":"No pair data was returned. This is not a zero-opportunity finding; the provider may be unavailable or query coverage may be limited."}
    return {"items":candidates[:limit],"source":"DexScreener API","updated_at":now_iso(),
      "data_status":"live_response" if candidates else "empty_response","queries_used":queries,
      "discovered_pairs":len(candidates),"provider_errors":errors[:3]}

def scan_crypto():
    """Compatibility alias for existing app routes; returns DEX pair candidates."""
    return scan_opportunities().get("items",[])

def market_overview():
    result={"source":"CoinGecko + DexScreener","updated_at":now_iso(),"data_status":"partial"}
    try:
        g=_cg("/global").get("data",{})
        dom=g.get("market_cap_percentage",{})
        result.update({"total_market_cap_usd":(g.get("total_market_cap") or {}).get("usd"),
          "total_volume_24h_usd":(g.get("total_volume") or {}).get("usd"),
          "market_cap_change_24h_pct":g.get("market_cap_change_percentage_24h_usd"),
          "btc_dominance_pct":dom.get("btc"),"global_source":"CoinGecko API","data_status":"live response"})
    except Exception as e:
        result["global_warning"]=str(e)[:150]
    return result

def analyze_asset(asset):
    query=str(asset or "").strip()
    if not query:
        return {"asset":"","status":"invalid_asset","message":"Enter a token symbol or contract address.","evidence":[],"counter_evidence":[],"action_state":"unverified"}
    try:
        pairs=_dex_search(query)
    except Exception as e:
        return {"asset":query.upper(),"status":"data_unavailable","message":f"DexScreener lookup failed: {str(e)[:150]}",
          "evidence":[],"counter_evidence":["No live pair data was verified."],"action_state":"unverified","source":"DexScreener API","updated_at":now_iso()}
    exact=[p for p in pairs if str((p.get("baseToken") or {}).get("symbol","")).lower()==query.lower()
           or str((p.get("baseToken") or {}).get("address","")).lower()==query.lower()
           or str((p.get("baseToken") or {}).get("name","")).lower()==query.lower()]
    chosen=exact or pairs
    candidates=[]
    for p in chosen:
        try: candidates.append(_pair_to_candidate(p))
        except Exception: pass
    candidates.sort(key=lambda x:(x.get("liquidity_usd") or 0,x.get("volume_24h_usd") or 0),reverse=True)
    if not candidates:
        return {"asset":query.upper(),"status":"not_found","message":"No matching DEX pair was returned by the provider. Try a contract address for better precision.",
          "evidence":[],"counter_evidence":["No pair match is not proof that the token does not exist."],"action_state":"unverified","source":"DexScreener API","updated_at":now_iso()}
    best=candidates[0]
    return {**best,"status":"ok","pair_alternatives":candidates[:8],
      "thesis":f"{best['asset']} has a reported DEX pair on {best.get('chain') or 'an unspecified chain'}; activity signals are observations, not a forecast.",
      "evidence":best["reasons"],"counter_evidence":best["risks"],
      "conditions_to_review":["Verify token contract and chain.","Inspect liquidity and likely slippage.","Compare activity across multiple time windows.","Review holder distribution and contract permissions using chain-specific sources."],
      "invalidation":"No chart-structure invalidation is calculated by this pair-data report.",
      "methodology":best["methodology"]}

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
      "warning":"Simplified estimate. Gaps, spread, slippage, leverage, funding, borrow costs and liquidation can increase losses."}
