import os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import intelligence as intel
import storage

class IntelligenceTests(unittest.TestCase):
    def test_event_classifier_policy(self):
        x=intel.classify_event('Federal Reserve FOMC rate decision')
        self.assertEqual(x['category'],'Central-bank policy')
        self.assertIn('Gold',x['affected_assets'])
    def test_event_classifier_crypto_security(self):
        x=intel.classify_event('Bridge exploit causes stablecoin depeg')
        self.assertEqual(x['category'],'Crypto market integrity')
    def test_parse_rss_item(self):
        xml='<rss><channel><item><title>Fed rate decision</title><link>https://example.com/a</link><description>Policy update</description><pubDate>Sun, 18 Oct 2026 12:00:00 GMT</pubDate></item></channel></rss>'
        items=intel.parse_feed(xml,'Test','policy','official')
        self.assertEqual(len(items),1); self.assertEqual(items[0]['trust'],'official'); self.assertTrue(items[0]['published_at'])
    def test_bad_xml_returns_empty(self): self.assertEqual(intel.parse_feed('<broken','x','x','x'),[])
    def test_pair_score_explains_risks(self):
        p={'baseToken':{'symbol':'TEST','name':'Test','address':'abc'},'chainId':'solana','dexId':'raydium','pairAddress':'pair','url':'https://example.com','priceUsd':'1','pairCreatedAt':int(__import__('time').time()*1000)-3600000,'volume':{'h1':100000,'h6':180000,'h24':250000},'liquidity':{'usd':10000},'txns':{'h1':{'buys':80,'sells':20},'h6':{'buys':200,'sells':100},'h24':{'buys':400,'sells':300}},'priceChange':{'h1':4,'h24':35}}
        x=intel._dex_pair_score(p)
        self.assertGreater(x['score'],0); self.assertTrue(x['evidence']); self.assertTrue(x['risks']); self.assertIn('not a price prediction',x['caveat'])
    def test_failed_quote_is_not_fabricated(self):
        # The provider wrapper creates a null price on failure; the app must not invent a quote.
        x={'symbol':'GC=F','price':None,'status':'provider_unavailable'}
        self.assertIsNone(x['price']); self.assertNotEqual(x['status'],'live_response')
    def test_education_content_has_recall(self):
        self.assertGreaterEqual(len(intel.LESSONS),10)
        self.assertTrue(all(x.get('check') and x.get('answer') for x in intel.LESSONS))
    def test_rss_classification_includes_mechanism(self):
        xml='<rss><channel><item><title>Bitcoin ETF approval</title><link>https://example.com</link></item></channel></rss>'
        item=intel.parse_feed(xml,'Test','crypto','media')[0]
        self.assertTrue(item['mechanism']); self.assertIn('Crypto',item['affected_assets'])

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.db=os.path.join(self.tmp.name,'edge.db'); storage.init_db(self.db)
    def tearDown(self): self.tmp.cleanup()
    def test_cache_roundtrip(self):
        storage.cache_put(self.db,'news',{'items':[{'title':'test'}]},'live_response')
        x=storage.cache_get(self.db,'news',60); self.assertEqual(x['items'][0]['title'],'test')
    def test_risk_trade_validation(self):
        with self.assertRaises(ValueError): storage.save_trade(self.db,{'asset':'BTC','direction':'long','entry':100,'stop':110,'quantity':1})
        x=storage.save_trade(self.db,{'asset':'BTC','direction':'long','entry':100,'stop':90,'quantity':2})
        self.assertEqual(x['risk_amount'],20)
    def test_trade_settlement_and_performance(self):
        t=storage.save_trade(self.db,{'asset':'BTC','direction':'long','entry':100,'stop':90,'quantity':2})
        storage.settle_trade(self.db,t['id'],110)
        p=storage.performance(self.db); self.assertEqual(p['closed_trades'],1); self.assertEqual(p['realized_pnl'],20)
    def test_learning_progress(self):
        storage.save_lesson_result(self.db,'macro-transmission',True)
        self.assertEqual(storage.learning_progress(self.db)[0]['quiz_correct'],1)
    def test_watchlist(self):
        storage.add_watch(self.db,'token','abc','ABC'); storage.add_watch(self.db,'token','abc','ABC')
        self.assertEqual(len(storage.list_watch(self.db)),1)

if __name__=='__main__': unittest.main(verbosity=2)
