"""Edge Intelligence: low-cost, source-aware multi-asset research engine.

No LLM is required. Explanations are deterministic, evidence-linked templates. External
provider failures are surfaced instead of being replaced with fabricated live data.
"""
from __future__ import annotations
import os, time, json, math, re, hashlib
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import quote
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import xml.etree.ElementTree as ET

TIMEOUT = int(os.getenv("EDGE_HTTP_TIMEOUT", "9"))
UA = os.getenv("EDGE_USER_AGENT", "EdgeIntelligence/2.0 (configure EDGE_USER_AGENT with contact email)")
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept": "application/json, application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.8"})

NEWS_FEEDS = [
    {"name":"Federal Reserve", "url":"https://www.federalreserve.gov/feeds/press_all.xml", "class":"policy", "trust":"official"},
    {"name":"ECB", "url":"https://www.ecb.europa.eu/rss/press.html", "class":"policy", "trust":"official"},
    {"name":"Bank of Japan", "url":"https://www.boj.or.jp/en/rss/whatsnew.xml", "class":"policy", "trust":"official"},
    {"name":"SEC filings", "url":"https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&output=atom", "class":"filings", "trust":"official"},
    {"name":"CoinDesk", "url":"https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml", "class":"crypto", "trust":"media"},
    {"name":"Cointelegraph", "url":"https://cointelegraph.com/rss", "class":"crypto", "trust":"media"},
    {"name":"The Block", "url":"https://www.theblock.co/rss.xml", "class":"crypto", "trust":"media"},
    {"name":"CNBC Markets", "url":"https://www.cnbc.com/id/100003114/device/rss/rss.html", "class":"finance", "trust":"media"},
    {"name":"WSJ Markets", "url":"https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "class":"finance", "trust":"media"},
]

SYMBOLS = [
    {"symbol":"BTC-USD", "name":"Bitcoin", "asset_class":"Crypto", "source":"Yahoo Finance chart", "mechanism":"Liquidity conditions, ETF flows, leverage and crypto-specific demand can dominate short horizons."},
    {"symbol":"ETH-USD", "name":"Ethereum", "asset_class":"Crypto", "source":"Yahoo Finance chart", "mechanism":"BTC beta, network activity, staking and application demand can drive relative performance."},
    {"symbol":"GC=F", "name":"Gold futures", "asset_class":"Gold", "source":"Yahoo Finance chart", "mechanism":"Real yields, USD, central-bank demand and risk hedging often matter; relationships can break down."},
    {"symbol":"SI=F", "name":"Silver futures", "asset_class":"Metals", "source":"Yahoo Finance chart", "mechanism":"Precious-metal demand mixes monetary sensitivity with industrial-cycle exposure."},
    {"symbol":"CL=F", "name":"WTI crude futures", "asset_class":"Energy", "source":"Yahoo Finance chart", "mechanism":"Supply shocks, inventories, OPEC decisions and growth expectations affect energy pricing."},
    {"symbol":"DX-Y.NYB", "name":"US Dollar Index", "asset_class":"FX / Macro", "source":"Yahoo Finance chart", "mechanism":"USD strength can tighten global financial conditions and influence gold and dollar-priced assets."},
    {"symbol":"^GSPC", "name":"S&P 500", "asset_class":"Equities", "source":"Yahoo Finance chart", "mechanism":"Earnings expectations, rates, risk appetite and index concentration affect broad equity pricing."},
    {"symbol":"^IXIC", "name":"Nasdaq Composite", "asset_class":"Equities", "source":"Yahoo Finance chart", "mechanism":"Growth-duration sensitivity makes yields and mega-cap earnings especially relevant."},
    {"symbol":"^VIX", "name":"VIX index", "asset_class":"Volatility", "source":"Yahoo Finance chart", "mechanism":"Implied equity volatility reflects demand for protection; it is not a direct forecast of direction."},
    {"symbol":"TLT", "name":"Long US Treasury ETF", "asset_class":"Rates proxy", "source":"Yahoo Finance chart", "mechanism":"Long-duration bond prices tend to react to changes in long-term yields and term premium."},
]

EVENT_RULES = [
    (r'gold|bullion|precious metal|central-bank gold', 'Precious metals / gold', ['Gold','USD','Rates','Equities'], 'Gold may respond to real yields, USD, central-bank demand and risk hedging; these relationships can break and the headline may already be priced in.'),
    (r'treasury yield|bond auction|term premium|yield curve|government bond|real yield', 'Rates / Treasury market', ['Rates','USD','Gold','Equities','Crypto'], 'Distinguish nominal yields from real yields, curve moves from level moves, and supply/term-premium shocks from central-bank expectations.'),
    (r'dollar index|currency intervention|yen intervention|foreign exchange|\\bfx\\b|euro rises|dollar rises', 'FX / USD', ['USD','Gold','Rates','Crypto','Equities'], 'FX reactions depend on relative policy expectations, positioning and funding; a stronger USD can tighten global conditions but is not a universal risk-off signal.'),
    (r'FOMC|federal reserve|rate decision|policy rate|interest rate decision', 'Central-bank policy', ['USD','Gold','Rates','Equities','Crypto'], 'The surprise versus expectations and the path implied by guidance matter more than the headline decision alone.'),
    (r'CPI|inflation|PCE price|producer price|PPI', 'Inflation', ['USD','Gold','Rates','Equities','Crypto'], 'Compare the print with consensus and inspect core components; a hot print may lift yields/USD, but positioning can reverse the reaction.'),
    (r'nonfarm|payroll|employment situation|unemployment|jobless claims|JOLTS', 'Labor market', ['USD','Rates','Equities','Crypto','Gold'], 'Labor surprises can change rate expectations; distinguish demand strength from wage/inflation pressure.'),
    (r'GDP|gross domestic product|PMI|ISM|retail sales|consumer confidence', 'Growth', ['Equities','Energy','USD','Rates','Crypto'], 'Growth data can help cyclical assets but hurt duration-sensitive assets if it pushes yields higher.'),
    (r'crude|petroleum|EIA|OPEC|oil inventory|natural gas', 'Energy supply / inventories', ['Energy','Inflation','Rates','Equities'], 'Inventory and supply surprises can shift oil prices and inflation expectations; distinguish headline stock changes from product demand.'),
    (r'tariff|sanction|war|attack|conflict|ceasefire|geopolit', 'Geopolitics / policy shock', ['Gold','Energy','USD','Equities','Crypto'], 'Map the direct supply-chain or sanction channel first; safe-haven reactions are conditional and can fade.'),
    (r'ETF|exchange-traded fund|SEC|approval|enforcement|lawsuit|regulation', 'Regulation / flows', ['Crypto','Equities'], 'Check whether the item is a new decision, a filing, a rumor, or a recycled story; the legal stage matters.'),
    (r'hack|exploit|outage|breach|bridge|stablecoin|depeg', 'Crypto market integrity', ['Crypto'], 'Verify the affected contract, funds at risk, chain status and official incident statements before extrapolating.'),
    (r'earnings|revenue|guidance|quarterly results|10-k|10-q|8-k', 'Company fundamentals', ['Equities','Crypto'], 'Compare actual results and forward guidance with expectations; a beat can sell off if guidance or positioning disappoints.'),
]

LESSONS = [
 {"id":"macro-transmission","title":"How macro data reaches asset prices","level":"Foundation","minutes":5,"body":"Markets price expectations, not just facts. A release matters when it changes the expected path of growth, inflation, policy rates, risk premia or cash flows. The same surprise can affect assets differently depending on positioning and the regime.","example":"A hotter-than-expected CPI print may lift nominal yields and the USD, weighing on gold or long-duration equities. But if the details are weak or the market was positioned for worse, the first move can reverse.","check":"Why can a strong economic report make stocks fall?","answer":"Because it can raise expected policy rates or discount rates more than it raises expected earnings.","tags":["macro","rates","gold","equities"]},
 {"id":"real-yields-gold","title":"Gold, real yields and the dollar","level":"Foundation","minutes":4,"body":"Gold does not have a fixed inverse relationship with yields or the dollar. Real yields are a useful opportunity-cost lens; USD, central-bank demand, geopolitical risk, ETF flows and positioning also matter.","example":"If nominal yields rise but inflation expectations rise faster, real yields can fall. Looking only at the nominal 10-year yield can misread the gold setup.","check":"What is the missing variable if nominal yields rise?","answer":"Inflation expectations, which help determine real yields.","tags":["gold","rates","USD"]},
 {"id":"expectations","title":"Consensus, surprise and revisions","level":"Foundation","minutes":4,"body":"A data point is not bullish or bearish in isolation. Compare actual versus consensus, prior values and revisions. The market may react to the components, revisions or forward guidance rather than the headline.","example":"Payrolls beat consensus, but prior months are revised sharply lower and wages cool. The headline alone misses the mixed message.","check":"What three things should you compare after a macro release?","answer":"Actual, consensus and prior/revisions (plus components and guidance where relevant).","tags":["events","macro"]},
 {"id":"liquidity","title":"Liquidity is part of the thesis","level":"Foundation","minutes":5,"body":"Displayed price is not executable price. Spread, depth, pool reserves, market impact, fees and the time needed to exit determine what a position is really worth. A token with high volume but shallow liquidity can be impossible to exit at the quoted price.","example":"A $20k position in a $40k-liquidity pool can materially move the pool and may suffer severe slippage on exit.","check":"Why isn't 24-hour volume enough to prove an entry is tradeable?","answer":"It says little about current depth, concentration, spread or the price impact of your order.","tags":["crypto","execution","risk"]},
 {"id":"asymmetry","title":"What an asymmetric trade actually means","level":"Intermediate","minutes":6,"body":"Asymmetry means the payoff distribution is favorable relative to the loss you can reasonably incur—not that the upside target is huge. Define a falsifiable thesis, plausible upside/downside scenarios, timing, liquidity, costs and invalidation. Avoid fake precision when probabilities are unknown.","example":"A catalyst is upcoming, the market's expectations appear stale, and downside can be defined. The idea is still weak if the catalyst is already priced in or liquidity makes the stop unrealistic.","check":"What must be specified before calling an idea asymmetric?","answer":"A thesis, catalyst/timing, plausible payoff scenarios, downside/invalidation, and execution costs.","tags":["risk","asymmetry"]},
 {"id":"positioning","title":"Positioning and crowded trades","level":"Intermediate","minutes":5,"body":"Price and fundamentals are only part of the picture. Funding, open interest, options skew, ETF flows and liquidation levels can reveal crowding. Crowded positioning can amplify a catalyst, but positioning data is incomplete and often ambiguous.","example":"Price rises with open interest and positive funding. This may indicate new leveraged longs, but not every OI increase is directional or necessarily bearish.","check":"Does rising open interest tell you whether traders are net long?","answer":"No. Every futures contract has both a long and a short; OI alone doesn't reveal directional net positioning.","tags":["crypto","derivatives"]},
 {"id":"event-study","title":"Test event reactions, don't narrate them","level":"Intermediate","minutes":7,"body":"For each event class, measure asset returns in consistent windows before and after releases, compare surprise sizes, and separate event effects from the broader market. Use point-in-time data to avoid look-ahead bias and evaluate across multiple regimes.","example":"Measure gold's 1h, 4h and 1d reaction to CPI surprises, but also control for USD and real-yield moves where data permits.","check":"Why is a single memorable event not enough evidence?","answer":"It may be an outlier or confounded by other news; repeated samples across regimes are needed.","tags":["research","macro"]},
 {"id":"source-quality","title":"Source quality and stale-data discipline","level":"Foundation","minutes":4,"body":"A reliable system records source, observation time, event time, delay and whether data is live, cached or unavailable. A failed API must not silently return a plausible-looking placeholder. Official primary sources confirm policy and releases; news outlets provide context, not final verification.","example":"A delayed gold benchmark should be labelled delayed, not displayed as a real-time executable quote.","check":"What should Edge do when a data provider fails?","answer":"Show the failure or stale cache explicitly, preserve last-updated time, and avoid generating a live signal from missing data.","tags":["data","research"]},
 {"id":"base-rates","title":"Base rates beat confident stories","level":"Intermediate","minutes":6,"body":"Before estimating the probability of a scenario, study how often similar setups worked historically. Group by regime, liquidity, asset type and catalyst. Use ranges and sample sizes; don't overfit a threshold to a small sample.","example":"A volume spike on a new token may often be followed by rapid mean reversion. A high score should not imply positive expectancy until forward outcomes are tested.","check":"What should be tested before a scanner score is called predictive?","answer":"Out-of-sample forward returns, hit rates, payoff, drawdown, fees/slippage and robustness across regimes.","tags":["research","statistics"]},
 {"id":"relative-value","title":"Relative value and cross-asset asymmetry","level":"Advanced","minutes":6,"body":"A relative-value idea asks whether one asset is mispriced versus a related asset, spread or macro driver. It can reduce broad market exposure but introduces basis, correlation-break and convergence-timing risks.","example":"Gold strengthens while the USD also rises. Investigate real yields, central-bank demand and positioning rather than assuming one relationship is broken permanently.","check":"What is a key risk in a relative-value trade?","answer":"The relationship can break or take longer to converge than capital and risk limits allow.","tags":["relative-value","gold","macro"]},
 {"id":"narrative-vs-flow","title":"Narrative is not the same as flow","level":"Intermediate","minutes":5,"body":"A compelling story can attract attention without producing durable demand. Confirm narrative catalysts with actual market activity, independent sources, liquidity and the ability to sustain buyers after the initial reaction.","example":"An exchange listing rumor is not equivalent to an official listing announcement, and the announcement itself may already be priced in.","check":"What should corroborate a narrative before it affects a trade thesis?","answer":"Primary-source confirmation, observable flows/activity, liquidity and a clear invalidation condition.","tags":["crypto","news"]},
 {"id":"risk-of-ruin","title":"Position sizing and risk of ruin","level":"Foundation","minutes":5,"body":"Position size should be driven by loss if the thesis fails, not confidence or upside target. Correlated positions can create one large hidden bet. Stops do not guarantee the exit price in gaps or illiquid pools.","example":"Three different crypto tokens may all be exposed to the same liquidity shock; treating them as independent risks underestimates portfolio exposure.","check":"Why can several different positions behave like one trade?","answer":"They may share the same underlying risk factors and become correlated during stress.","tags":["risk","portfolio"]},
 {"id":"revision-risk","title":"Revisions and data-vintage bias","level":"Advanced","minutes":5,"body":"Macro data is often revised. A backtest using the latest revised history can know more than a trader did at the time. Use release timestamps and point-in-time vintages where possible; FRED/ALFRED documents real-time periods and historical vintages.","example":"A recession indicator may look clean in revised data but would have been noisy using the numbers available on the original release date.","check":"What is look-ahead bias in macro research?","answer":"Using revised or future information that was not available at the decision time.","tags":["macro","research"]},
]


def utcnow(): return datetime.now(timezone.utc)
def iso_now(): return utcnow().isoformat()
def num(v):
    try:
        n=float(v)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError): return None

def http_json(url, params=None, headers=None):
    r=SESSION.get(url, params=params, headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def http_text(url, params=None):
    r=SESSION.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text

def classify_event(text):
    t=(text or '').lower()
    for pattern, category, assets, mechanism in EVENT_RULES:
        if re.search(pattern, t, re.I):
            return {"category":category,"affected_assets":assets,"mechanism":mechanism}
    return {"category":"General market / policy","affected_assets":["Cross-asset"],"mechanism":"Check the primary source and identify the transmission channel before assigning direction."}

def _tag(node, name):
    for child in list(node):
        if child.tag.split('}')[-1].lower()==name.lower(): return (child.text or '').strip()
    return ''

def parse_feed(xml_text, source, source_class, trust):
    try: root=ET.fromstring(xml_text)
    except ET.ParseError: return []
    out=[]
    for node in root.iter():
        tag=node.tag.split('}')[-1].lower()
        if tag not in ('item','entry'): continue
        title=_tag(node,'title')
        link=_tag(node,'link')
        if not link:
            for ch in list(node):
                if ch.tag.split('}')[-1].lower()=='link':
                    link=ch.attrib.get('href',''); break
        summary=_tag(node,'description') or _tag(node,'summary') or _tag(node,'content')
        published=_tag(node,'pubdate') or _tag(node,'published') or _tag(node,'updated') or _tag(node,'date')
        if not title: continue
        dt=None
        if published:
            try:
                dt=parsedate_to_datetime(published) if re.search(r'[A-Za-z]{3},',published) else datetime.fromisoformat(published.replace('Z','+00:00'))
                if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
                dt=dt.astimezone(timezone.utc).isoformat()
            except Exception: dt=None
        classification=classify_event(title+' '+summary)
        out.append({"id":hashlib.sha1((source+'|'+title+'|'+link).encode()).hexdigest()[:16],"title":re.sub('<[^>]+>',' ',title).strip(),"summary":re.sub('<[^>]+>',' ',summary).strip()[:700],"url":link,"source":source,"source_class":source_class,"trust":trust,"published_at":dt,"observed_at":iso_now(),"category":classification['category'],"affected_assets":classification['affected_assets'],"mechanism":classification['mechanism']})
        if len(out)>=30: break
    return out

def fetch_news():
    items=[]; errors=[]
    def one(feed): return feed, parse_feed(http_text(feed['url']),feed['name'],feed['class'],feed['trust'])
    with ThreadPoolExecutor(max_workers=min(7,len(NEWS_FEEDS))) as pool:
        futures=[pool.submit(one,feed) for feed in NEWS_FEEDS]
        for future in as_completed(futures):
            try:
                feed, parsed=future.result(); items.extend(parsed)
            except Exception as e: errors.append(f"feed request: {type(e).__name__}")
    # dedupe by URL/title, sort with dated items first
    unique={}
    for item in items: unique[item['id']]=item
    items=list(unique.values())
    items.sort(key=lambda x:x.get('published_at') or '',reverse=True)
    return {"items":items[:100],"status":"live_response" if items else "provider_unavailable","updated_at":iso_now(),"errors":errors,"sources":[f['name'] for f in NEWS_FEEDS]}

def fetch_calendar():
    start=utcnow().date().isoformat(); end=(utcnow().date()+timedelta(days=21)).isoformat()
    url='https://www.financecalendar.com/wp-json/fc/v1/calendar'
    try:
        payload=http_json(url,params={"from":start,"to":end,"limit":500})
        raw=(payload.get('events') or []) if isinstance(payload,dict) else payload if isinstance(payload,list) else []
        events=[]
        for e in raw if isinstance(raw,list) else []:
            name=e.get('name') or e.get('title') or e.get('event') or 'Economic event'
            cl=classify_event(name+' '+str(e.get('category','')))
            dt=e.get('time_utc') or e.get('datetime') or e.get('date')
            impact=(e.get('impact') or 'medium').lower()
            events.append({"id":str(e.get('id') or hashlib.sha1((name+str(dt)).encode()).hexdigest()[:14]),"title":name,"date":dt,"country":e.get('country') or e.get('region') or 'Global/US calendar',"impact":impact,"category":e.get('category') or cl['category'],"actual":e.get('actual'),"consensus":e.get('consensus'),"prior":e.get('prior'),"url":e.get('url') or 'https://www.financecalendar.com/',"affected_assets":cl['affected_assets'],"mechanism":cl['mechanism'],"source":"FinanceCalendar","trust":"calendar aggregator"})
        events.sort(key=lambda x:x.get('date') or '')
        return {"items":events,"status":"live_response" if events else "empty_response","updated_at":iso_now(),"errors":[],"attribution":{"name":"FinanceCalendar","url":"https://www.financecalendar.com/api/"}}
    except Exception as e:
        return {"items":[],"status":"provider_unavailable","updated_at":iso_now(),"errors":[f"FinanceCalendar: {type(e).__name__}"],"attribution":{"name":"FinanceCalendar","url":"https://www.financecalendar.com/api/"}}

def fetch_yahoo_quote(symbol):
    url='https://query1.finance.yahoo.com/v8/finance/chart/'+quote(symbol,safe='')
    data=http_json(url,params={"range":"5d","interval":"1d"})
    result=(data.get('chart') or {}).get('result') or []
    if not result: raise ValueError('No quote data')
    r=result[0]; meta=r.get('meta') or {}; q=((r.get('indicators') or {}).get('quote') or [{}])[0]
    closes=[x for x in (q.get('close') or []) if num(x) is not None]
    if not closes: raise ValueError('No close data')
    last=num(closes[-1]); prev=num(closes[-2]) if len(closes)>1 else num(meta.get('chartPreviousClose'))
    change=((last/prev)-1)*100 if last is not None and prev else None
    ts=(r.get('timestamp') or [])
    observed=datetime.fromtimestamp(ts[-1],timezone.utc).isoformat() if ts else None
    return {"symbol":symbol,"name":meta.get('longName') or meta.get('shortName') or symbol,"price":last,"change_pct":change,"currency":meta.get('currency') or 'USD',"market_state":meta.get('marketState'),"market_time":observed,"source":"Yahoo Finance public chart endpoint","status":"live_response","note":"Indicative reference quote; may be delayed and is not an executable quote."}

def fetch_cross_asset():
    results=[]; errors=[]
    def one(item):
        try:
            q=fetch_yahoo_quote(item['symbol']); q.update({"asset_class":item['asset_class'],"mechanism":item['mechanism']}); return q, None
        except Exception as e:
            return {"symbol":item['symbol'],"name":item['name'],"asset_class":item['asset_class'],"price":None,"change_pct":None,"source":item['source'],"status":"provider_unavailable","note":"Quote unavailable; no placeholder value shown.","mechanism":item['mechanism']}, f"{item['symbol']}: {type(e).__name__}"
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures=[pool.submit(one,item) for item in SYMBOLS]
        for future in as_completed(futures):
            item,error=future.result(); results.append(item)
            if error: errors.append(error)
    order={x['symbol']:i for i,x in enumerate(SYMBOLS)}
    results.sort(key=lambda x:order.get(x.get('symbol'),999))
    return {"items":results,"status":"live_response" if any(x.get('price') is not None for x in results) else "provider_unavailable","updated_at":iso_now(),"errors":errors}

def fetch_crypto_overview():
    try:
        data=http_json('https://api.coingecko.com/api/v3/global')
        d=data.get('data') or {}
        return {"status":"live_response","source":"CoinGecko global endpoint","updated_at":iso_now(),"market_cap_usd":(d.get('total_market_cap') or {}).get('usd'),"volume_24h_usd":(d.get('total_volume') or {}).get('usd'),"btc_dominance_pct":(d.get('market_cap_percentage') or {}).get('btc'),"market_cap_change_24h_pct":d.get('market_cap_change_percentage_24h_usd'),"active_cryptocurrencies":d.get('active_cryptocurrencies'),"note":"Aggregate market data; provider limits or outages may affect availability."}
    except Exception as e:
        return {"status":"provider_unavailable","source":"CoinGecko global endpoint","updated_at":iso_now(),"error":type(e).__name__,"note":"Unavailable; no live values inferred."}

def _dex_pair_score(p):
    base=p.get('baseToken') or {}; tx=p.get('txns') or {}; h1=tx.get('h1') or {}; h6=tx.get('h6') or {}; h24=tx.get('h24') or {}; vol=p.get('volume') or {}; liq=p.get('liquidity') or {}; ch=p.get('priceChange') or {}
    v1=num(vol.get('h1')) or 0; v6=num(vol.get('h6')) or 0; v24=num(vol.get('h24')) or 0; l=num(liq.get('usd')) or 0
    b1=num(h1.get('buys')) or 0; s1=num(h1.get('sells')) or 0; b24=num(h24.get('buys')) or 0; s24=num(h24.get('sells')) or 0
    t1=b1+s1; t24=b24+s24; ratio=b24/t24 if t24 else None
    accel=v1/(v6/6) if v1>0 and v6>0 else None
    tx_accel=t1/(t24/24) if t1>0 and t24>0 else None
    created=num(p.get('pairCreatedAt')); age=max(0,(time.time()*1000-created)/3600000) if created else None
    score=0; evidence=[]; risks=[]
    if accel is not None:
        points= min(25,max(0,(accel-1)*7))
        score+=points
        if accel>=1.5: evidence.append(f"1h volume is {accel:.1f}× the 6h hourly average.")
    if tx_accel is not None:
        points=min(15,max(0,(tx_accel-1)*5)); score+=points
        if tx_accel>=1.5: evidence.append(f"1h transaction pace is {tx_accel:.1f}× its 24h hourly average.")
    if ratio is not None and t24>=20:
        if ratio>=.62: score+=10; evidence.append(f"Buys are {ratio:.0%} of reported 24h transactions.")
        elif ratio<.42: risks.append(f"Sell-heavy flow: buys are {ratio:.0%} of reported 24h transactions.")
    if l>=100000: score+=10; evidence.append(f"Reported pool liquidity is ${l:,.0f}.")
    elif l<20000: risks.append(f"Thin pool liquidity (${l:,.0f}); execution impact may be severe.")
    if age is not None and age<72: score+=8; evidence.append(f"Pool age is approximately {age:.1f} hours.")
    c24=num(ch.get('h24'))
    if c24 is not None and c24>25: risks.append(f"Extended move: reported 24h price change is +{c24:.1f}%.")
    if c24 is not None and c24<-25: risks.append(f"Large 24h drawdown: {c24:.1f}%.")
    if v24>0 and l>0 and v24/l>20: risks.append("Very high 24h volume relative to pool liquidity; verify organic flow and exit depth.")
    stage='Activity developing' if score>=28 else 'Early watch' if score>=15 else 'Low evidence'
    return {"asset":base.get('symbol') or base.get('name') or 'Unknown','name':base.get('name') or base.get('symbol') or 'Unknown',"chain":p.get('chainId'),'dex':p.get('dexId'),'pair_address':p.get('pairAddress'),'token_address':base.get('address'),'pair_url':p.get('url'),'price_usd':num(p.get('priceUsd')),'liquidity_usd':l,'volume_1h_usd':v1,'volume_6h_usd':v6,'volume_24h_usd':v24,'transactions_1h':t1,'transactions_24h':t24,'buy_ratio_24h':ratio,'volume_liquidity_ratio':v24/l if l else None,'change_1h_pct':num(ch.get('h1')),'change_24h_pct':c24,'pair_age_hours':age,'score':round(score,1),'stage':stage,'evidence':evidence,'risks':risks,'source':'DexScreener public API','status':'observed','updated_at':iso_now(),'caveat':'Activity screen only. It is not a price prediction, safety audit or recommendation.'}

def fetch_opportunities():
    queries=[x.strip() for x in os.getenv('EDGE_DISCOVERY_QUERIES','solana;base;ethereum;bnb;avalanche;new pair;memecoin').split(';') if x.strip()]
    pairs={}; errors=[]
    for q in queries:
        try:
            data=http_json('https://api.dexscreener.com/latest/dex/search',params={'q':q})
            for p in data.get('pairs') or []:
                key=(p.get('chainId'),p.get('pairAddress'))
                if key[1]: pairs[key]=p
        except Exception as e: errors.append(f"DexScreener query '{q}': {type(e).__name__}")
    items=[_dex_pair_score(p) for p in pairs.values()]
    items=[x for x in items if x.get('liquidity_usd',0)>0 and x.get('volume_24h_usd',0)>0]
    items.sort(key=lambda x:(x['score'],x['volume_1h_usd']),reverse=True)
    return {"items":items[:100],"status":"live_response" if items else "provider_unavailable" if errors else "empty_response","updated_at":iso_now(),"errors":errors,"queries":queries,"source":"DexScreener public API"}

def _impact_story(title, assets, mechanism, actual=None, consensus=None, prior=None):
    parts=[]
    if actual is not None and consensus is not None:
        a=num(actual); c=num(consensus)
        if a is not None and c is not None:
            parts.append(f"Reported actual {a:g} versus consensus {c:g} (surprise {a-c:+g}).")
    if prior is not None: parts.append(f"Prior: {prior}.")
    parts.append(mechanism)
    parts.append("Direction is conditional: compare the surprise with positioning, revisions and the price reaction; do not infer a trade from the event label alone.")
    return ' '.join(parts)

def build_asymmetry_watch(news, events, cross_asset, opportunities):
    """Evidence queue, not trade signals. It ranks research tasks by observable catalysts."""
    ideas=[]; now=utcnow()
    for ev in (events.get('items') or []):
        date=ev.get('date') or ''
        future=False; hours=None
        try:
            dt=datetime.fromisoformat(date.replace('Z','+00:00'))
            if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
            hours=(dt-now).total_seconds()/3600; future=hours>=0
        except Exception: pass
        if future and hours is not None and hours<=168:
            impact=(ev.get('impact') or 'medium').lower(); score=35 if impact=='high' else 24 if impact=='medium' else 12
            ideas.append({"id":"event-"+str(ev.get('id')),"type":"Catalyst watch","title":ev.get('title','Upcoming event'),"score":score,"confidence":"Catalyst known; market reaction unknown","why_now":f"Scheduled in approximately {hours:.0f} hours.","assets":ev.get('affected_assets') or ['Cross-asset'],"thesis":"Research whether current pricing and positioning are misaligned with plausible event outcomes.","confirmations":["Official release time and primary source verified","Consensus and prior values captured","Pre-event positioning and current price reaction recorded"],"invalidation":["Market has already repriced the scenario","No measurable surprise or price response","Liquidity or event timing is uncertain"],"risk":"Binary event risk, whipsaw and gap risk; avoid treating consensus as certainty.","source":ev.get('source'),'source_url':ev.get('url'),'evidence_status':'scheduled catalyst; no directional signal','updated_at':iso_now()})
    for q in (opportunities.get('items') or [])[:15]:
        if q.get('score',0)>=20:
            ideas.append({"id":"dex-"+str(q.get('chain'))+"-"+str(q.get('pair_address')),"type":"On-chain activity watch","title":f"{q.get('asset')} · {q.get('chain')}","score":min(50,round(q.get('score',0))),"confidence":"Activity observed; direction unproven","why_now":"; ".join(q.get('evidence') or ['Activity metrics changed']) or 'Elevated observed activity.',"assets":[q.get('asset') or 'Token'],"thesis":"Check whether activity is organic and whether executable liquidity supports a trade-sized position.","confirmations":["Verify token contract and pool address","Check holder/deployer concentration and contract permissions","Compare volume with liquidity and independent trade flow"],"invalidation":q.get('risks') or ["Activity decelerates or is not independently corroborated"],"risk":"New-token activity is vulnerable to wash trading, snipers, MEV, concentrated ownership and abrupt liquidity loss.","source":"DexScreener","source_url":q.get('pair_url'),'evidence_status':'screening candidate, not a trade signal','updated_at':q.get('updated_at')})
    # Cross-asset relative-move investigations are hypotheses, never directional calls.
    by={x.get('symbol'):x for x in (cross_asset.get('items') or [])}
    gold=by.get('GC=F'); usd=by.get('DX-Y.NYB'); sp=by.get('^GSPC'); vix=by.get('^VIX'); btc=by.get('BTC-USD')
    if gold and usd and gold.get('change_pct') is not None and usd.get('change_pct') is not None and gold['change_pct']>0 and usd['change_pct']>0:
        ideas.append({"id":"rv-gold-usd","type":"Relative-value investigation","title":"Gold and USD rising together","score":32,"confidence":"Cross-asset divergence to investigate","why_now":f"Gold {gold['change_pct']:+.2f}% and USD index {usd['change_pct']:+.2f}% over provider's latest daily window.","assets":["Gold","USD","Real yields"],"thesis":"Check real yields, central-bank gold demand and geopolitical hedging before concluding that a relationship is mispriced.","confirmations":["Verify synchronized timestamps","Check real-yield and Treasury data","Review gold ETF/central-bank flow context"],"invalidation":["Quotes are stale or not time-aligned","Move explained by a clear fundamental shock","No historical relationship edge after costs"],"risk":"Cross-asset relationships are unstable and this observation alone is not a signal.","source":"Yahoo Finance public chart endpoint","evidence_status":"conditional relative-value research prompt","updated_at":iso_now()})
    eth=by.get('ETH-USD')
    if btc and eth and btc.get('change_pct') is not None and eth.get('change_pct') is not None and abs(btc['change_pct']-eth['change_pct'])>=2:
        ideas.append({"id":"rv-btc-eth","type":"Relative-strength investigation","title":"BTC / ETH relative performance diverges","score":26,"confidence":"Relative move observed; cause unconfirmed","why_now":f"BTC {btc['change_pct']:+.2f}% vs ETH {eth['change_pct']:+.2f}% over provider's latest daily window.","assets":["Bitcoin","Ethereum","Crypto beta"],"thesis":"Investigate whether flows, ETF demand, network-specific catalysts or leverage explain the relative move before assuming mean reversion.","confirmations":["Align quote timestamps and time windows","Check relative volume, funding and open interest","Review BTC/ETH-specific catalyst news"],"invalidation":["A fundamental catalyst justifies the divergence","The relationship has no stable historical edge","Spread costs and volatility overwhelm the expected convergence"],"risk":"Relative strength can persist; pair trades add basis and convergence-timing risk.","source":"Yahoo Finance public chart endpoint","evidence_status":"conditional relative-value research prompt","updated_at":iso_now()})
    if sp and vix and sp.get('change_pct') is not None and vix.get('change_pct') is not None and sp['change_pct']>0 and vix['change_pct']>5:
        ideas.append({"id":"rv-spx-vix","type":"Regime watch","title":"Equities rising while volatility rises","score":28,"confidence":"Regime anomaly to investigate","why_now":f"S&P 500 {sp['change_pct']:+.2f}%; VIX {vix['change_pct']:+.2f}%.","assets":["Equities","Volatility"],"thesis":"Check whether event hedging, index concentration or intraday timing explains the divergence.","confirmations":["Use synchronized timestamps","Inspect options term structure and breadth","Check whether the move persists beyond one observation"],"invalidation":["Daily bars are asynchronous","The divergence disappears on intraday data","No persistent conditional edge in historical samples"],"risk":"VIX is not a directional forecast and daily changes can mislead.","source":"Yahoo Finance public chart endpoint","evidence_status":"research prompt only","updated_at":iso_now()})
    ideas.sort(key=lambda x:(x['score'],x['type']=='Catalyst watch'),reverse=True)
    return {"items":ideas[:40],"status":"research_queue","updated_at":iso_now(),"note":"Rank is an evidence-priority heuristic, not probability of profit or expected return."}

def dashboard_payload(fetcher=None):
    # For web request handlers; provider caching is handled by the application storage layer.
    fetcher=fetcher or {}
    overview=(fetcher.get('overview') or fetch_crypto_overview())
    cross=(fetcher.get('cross_asset') or fetch_cross_asset())
    news=(fetcher.get('news') or fetch_news())
    events=(fetcher.get('events') or fetch_calendar())
    opps=(fetcher.get('opportunities') or fetch_opportunities())
    ideas=build_asymmetry_watch(news,events,cross,opps)
    return {"updated_at":iso_now(),"overview":overview,"cross_asset":cross,"news":news,"events":events,"opportunities":opps,"asymmetry":ideas,"education":{"lessons":LESSONS,"count":len(LESSONS),"method":"Curated, deterministic lessons; no per-request LLM cost."},"data_policy":{"live_means":"A provider returned a successful response; individual quote timestamps still matter.","cached_means":"Stored provider response within cache window.","unavailable_means":"No value is fabricated when a provider fails.","source_quality":"Official sources for primary policy/releases; media for context; market-data providers for observations."}}
