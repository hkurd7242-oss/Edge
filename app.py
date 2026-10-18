"""Edge — source-aware, low-cost cross-asset trading intelligence."""
import os, json, time, traceback, threading, hmac
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, jsonify, request, render_template_string, send_from_directory
import intelligence as intel
import storage

APP_DIR=os.path.dirname(os.path.abspath(__file__))
DB_PATH=os.environ.get('EDGE_DB_PATH',os.path.join(APP_DIR,'data','edge.db'))
os.makedirs(os.path.dirname(DB_PATH),exist_ok=True)
storage.init_db(DB_PATH)
app=Flask(__name__); app.config['JSON_SORT_KEYS']=False
ACCESS_TOKEN=os.environ.get('EDGE_ACCESS_TOKEN','').strip()
with open(os.path.join(APP_DIR,'index.html'),encoding='utf-8') as f: HTML=f.read()
CACHE_TTLS={'overview':180,'cross_asset':180,'news':300,'events':900,'opportunities':180,'asymmetry':180}
_refresh_lock=threading.Lock()

def utcnow(): return datetime.now(timezone.utc).isoformat()
def cached(key,ttl=None):
    ttl=CACHE_TTLS.get(key,300) if ttl is None else ttl
    item=storage.cache_get(DB_PATH,key,ttl)
    if item: item['data_status']='cached'; return item
    item=storage.cache_get(DB_PATH,key,None)
    if item: item['data_status']='stale_cache'; return item
    return {'items':[],'status':'not_loaded','data_status':'not_loaded','updated_at':None,'errors':[]}

def refresh_all():
    """Fetch sources concurrently, store explicit provider states, then derive research queue."""
    jobs={
        'overview':intel.fetch_crypto_overview,
        'cross_asset':intel.fetch_cross_asset,
        'news':intel.fetch_news,
        'events':intel.fetch_calendar,
        'opportunities':intel.fetch_opportunities,
    }
    results={}; errors=[]
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures={pool.submit(fn):key for key,fn in jobs.items()}
        for future,key in futures.items():
            try: results[key]=future.result()
            except Exception as exc: results[key]={'status':'provider_unavailable','updated_at':utcnow(),'errors':[f'{key}: {type(exc).__name__}'],'items':[]}; errors.extend(results[key]['errors'])
    for key,payload in results.items():
        status=payload.get('status','unknown')
        storage.cache_put(DB_PATH,key,payload,status)
    for item in (results.get('opportunities') or {}).get('items',[]):
        try: storage.save_snapshot(DB_PATH,item)
        except Exception: pass
    combined={key:results.get(key) or cached(key,None) for key in jobs}
    asym=intel.build_asymmetry_watch(combined['news'],combined['events'],combined['cross_asset'],combined['opportunities'])
    storage.cache_put(DB_PATH,'asymmetry',asym,asym.get('status','research_queue'))
    storage.set_state(DB_PATH,'last_attempt',utcnow())
    storage.set_state(DB_PATH,'last_success',utcnow() if any((x.get('status')=='live_response') for x in results.values()) else 'no_provider_success')
    storage.set_state(DB_PATH,'last_status',json.dumps({k:v.get('status') for k,v in results.items()}))
    storage.set_state(DB_PATH,'last_error','; '.join(errors+[e for v in results.values() for e in (v.get('errors') or [])])[:1200])
    storage.set_state(DB_PATH,'last_count',len((results.get('opportunities') or {}).get('items') or []))
    return build_dashboard(force_cached=True)

def build_dashboard(force_cached=False):
    pieces={k:cached(k,0 if force_cached else CACHE_TTLS.get(k,300)) for k in ('overview','cross_asset','news','events','opportunities','asymmetry')}
    # Recompute asymmetry from whatever is available, but do not write synthetic market observations.
    if not pieces['asymmetry'].get('items'):
        pieces['asymmetry']=intel.build_asymmetry_watch(pieces['news'],pieces['events'],pieces['cross_asset'],pieces['opportunities'])
    progress=storage.learning_progress(DB_PATH)
    state=storage.get_state(DB_PATH)
    return {'updated_at':utcnow(),'overview':pieces['overview'],'cross_asset':pieces['cross_asset'],'news':pieces['news'],'events':pieces['events'],'opportunities':pieces['opportunities'],'asymmetry':pieces['asymmetry'],'education':{'lessons':intel.LESSONS,'count':len(intel.LESSONS),'progress':progress,'method':'Curated deterministic lessons; no per-request LLM cost.'},'watchlist':storage.list_watch(DB_PATH),'alerts':storage.latest_alerts(DB_PATH),'worker':state,'data_policy':{'live_means':'Provider returned a successful response; individual quote timestamps still matter.','cached_means':'Stored provider response within cache window.','unavailable_means':'No value is fabricated when a provider fails.','source_quality':'Official sources confirm primary policy/releases; media provides context; data vendors provide observations.'},'attribution':[{'name':'FinanceCalendar','url':'https://www.financecalendar.com/api/','reason':'Economic calendar data; link attribution required.'},{'name':'CoinGecko','url':'https://www.coingecko.com/en/api','reason':'Aggregate crypto market context.'},{'name':'DexScreener','url':'https://docs.dexscreener.com/api/reference','reason':'DEX pair discovery.'}]}

@app.before_request
def protect_api():
    if ACCESS_TOKEN and request.path.startswith('/api/'):
        supplied=request.headers.get('X-Edge-Token','')
        if not hmac.compare_digest(supplied,ACCESS_TOKEN): return jsonify({'error':'authentication_required'}),401

@app.get('/')
def home(): return render_template_string(HTML)

@app.get('/static/<path:asset>')
def flat_static(asset):
    # Flat-file GitHub upload compatibility: static assets live beside app.py.
    allowed={'edge-icon.svg','manifest.webmanifest','sw.js'}
    if asset not in allowed: return jsonify({'error':'not_found'}),404
    return send_from_directory(APP_DIR, asset)
@app.get('/health')
def health():
    return jsonify({'ok':True,'app':'Edge Cross-Asset Intelligence','time':utcnow(),'database':os.path.exists(DB_PATH),'worker':storage.get_state(DB_PATH)})
@app.get('/api/dashboard')
def dashboard():
    if request.args.get('refresh')=='1':
        try: return jsonify(refresh_all())
        except Exception as e: return jsonify({'error':'refresh_failed','message':type(e).__name__,'dashboard':build_dashboard()}),502
    return jsonify(build_dashboard())
@app.post('/api/refresh')
def refresh():
    # Public app deployments should not let anonymous callers fan out provider requests repeatedly.
    last=storage.get_state(DB_PATH).get('last_manual_refresh')
    if last:
        try:
            elapsed=(datetime.now(timezone.utc)-datetime.fromisoformat(last)).total_seconds()
            if elapsed<45: return jsonify({'error':'refresh_rate_limited','retry_after_seconds':int(45-elapsed)+1}),429
        except Exception: pass
    if not _refresh_lock.acquire(blocking=False): return jsonify({'error':'refresh_in_progress'}),429
    try:
        storage.set_state(DB_PATH,'last_manual_refresh',utcnow())
        return jsonify(refresh_all())
    except Exception as e:
        storage.set_state(DB_PATH,'last_error',f'{type(e).__name__}: {e}')
        return jsonify({'error':'refresh_failed','message':type(e).__name__,'dashboard':build_dashboard()}),502
    finally: _refresh_lock.release()
@app.get('/api/events')
def events(): return jsonify(cached('events',0))
@app.get('/api/news')
def news(): return jsonify(cached('news',0))
@app.get('/api/markets')
def markets(): return jsonify({'overview':cached('overview',0),'cross_asset':cached('cross_asset',0)})
@app.get('/api/opportunities')
def opportunities(): return jsonify(cached('opportunities',0))
@app.get('/api/asymmetry')
def asymmetry():
    d=cached('asymmetry',0)
    if not d.get('items'): d=intel.build_asymmetry_watch(cached('news',0),cached('events',0),cached('cross_asset',0),cached('opportunities',0))
    return jsonify(d)
@app.get('/api/learn')
def learn(): return jsonify({'lessons':intel.LESSONS,'progress':storage.learning_progress(DB_PATH)})
@app.post('/api/learn/<lesson_id>/answer')
def answer_lesson(lesson_id):
    lesson=next((x for x in intel.LESSONS if x['id']==lesson_id),None)
    if not lesson: return jsonify({'error':'lesson_not_found'}),404
    body=request.get_json(silent=True) or {}; answer=str(body.get('answer','')).strip().lower()
    # Quiz choices are authored from the lesson's known answer; match meaningful keywords rather than exact wording.
    expected=lesson['answer'].lower()
    terms=[w for w in re_words(expected) if len(w)>4]
    correct=bool(answer) and (answer in expected or sum(w in answer for w in terms)>=max(1,min(2,len(terms))))
    storage.save_lesson_result(DB_PATH,lesson_id,correct)
    return jsonify({'correct':correct,'expected':lesson['answer'],'progress':storage.learning_progress(DB_PATH)})
def re_words(text):
    import re
    return re.findall(r'[a-z0-9]+',text)
@app.get('/api/watchlist')
def watchlist(): return jsonify({'items':storage.list_watch(DB_PATH)})
@app.post('/api/watchlist')
def add_watch():
    body=request.get_json(silent=True) or {}; kind=str(body.get('kind','asset'))[:40]; identifier=str(body.get('identifier','')).strip()[:160]; label=str(body.get('label') or identifier).strip()[:160]
    if not identifier: return jsonify({'error':'identifier_required'}),400
    return jsonify(storage.add_watch(DB_PATH,kind,identifier,label)),201
@app.delete('/api/watchlist/<int:item_id>')
def remove_watch(item_id): return jsonify({'deleted':storage.delete_watch(DB_PATH,item_id)})
@app.post('/api/risk')
def risk():
    b=request.get_json(silent=True) or {}
    try:
        equity=float(b['equity']); risk_pct=float(b['risk_pct']); entry=float(b['entry']); stop=float(b['stop']); direction=str(b.get('direction','long')).lower()
        if min(equity,risk_pct,entry,stop)<=0 or risk_pct>100 or direction not in ('long','short'): raise ValueError('Use positive values, risk 0–100%, and long/short direction.')
        if (direction=='long' and stop>=entry) or (direction=='short' and stop<=entry): raise ValueError('Stop must be below entry for long and above entry for short.')
        risk_cash=equity*risk_pct/100; qty=risk_cash/abs(entry-stop); notional=qty*entry
        return jsonify({'risk_cash':risk_cash,'quantity':qty,'notional':notional,'notional_pct_equity':notional/equity*100,'stop_distance_pct':abs(entry-stop)/entry*100,'note':'Excludes fees, slippage, funding and gaps. Stop execution is not guaranteed.'})
    except (KeyError,TypeError,ValueError) as e: return jsonify({'error':str(e)}),400
@app.get('/api/trades')
def trades(): return jsonify({'items':storage.list_trades(DB_PATH)})
@app.post('/api/trades')
def add_trade():
    try: return jsonify(storage.save_trade(DB_PATH,request.get_json(silent=True) or {})),201
    except (KeyError,ValueError,TypeError) as e: return jsonify({'error':str(e)}),400
@app.post('/api/trades/<int:trade_id>/settle')
def close_trade(trade_id):
    try: return jsonify(storage.settle_trade(DB_PATH,trade_id,float((request.get_json(silent=True) or {})['exit'])))
    except (KeyError,ValueError,TypeError) as e: return jsonify({'error':str(e)}),400
@app.get('/api/performance')
def performance(): return jsonify(storage.performance(DB_PATH))

if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.environ.get('PORT','5060')),debug=False)
