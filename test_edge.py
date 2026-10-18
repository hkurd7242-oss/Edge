import os, tempfile, unittest
from unittest.mock import patch
import engine
from storage import init_db, save_snapshot, latest_alerts

class EdgeTests(unittest.TestCase):
    def test_pair_activity_score_and_risk(self):
        p={"chainId":"solana","dexId":"raydium","pairAddress":"pair1","url":"https://example.test",
          "baseToken":{"symbol":"ABC","name":"Alpha","address":"token1"},"quoteToken":{"symbol":"SOL"},
          "priceUsd":"1.25","pairCreatedAt":int(__import__("time").time()*1000)-3600000,
          "txns":{"h1":{"buys":30,"sells":5},"h6":{"buys":80,"sells":30},"h24":{"buys":250,"sells":100}},
          "volume":{"h1":10000,"h6":30000,"h24":80000},"priceChange":{"h1":5,"h6":10,"h24":12},
          "liquidity":{"usd":150000},"marketCap":500000}
        x=engine._pair_to_candidate(p)
        self.assertEqual(x["asset"],"ABC")
        self.assertGreater(x["score"],0)
        self.assertEqual(x["action_state"],"research_only")
        self.assertIn("liquidity_usd",x)

    def test_snapshot_creates_alert_on_score_cross(self):
        with tempfile.TemporaryDirectory() as d:
            db=os.path.join(d,"edge.db"); init_db(db)
            low={"asset":"ABC","chain":"sol","pair_address":"p1","score":10,"volume_1h_usd":10,"updated_at":"2026-01-01T00:00:00Z"}
            high={"asset":"ABC","chain":"sol","pair_address":"p1","score":40,"volume_1h_usd":50,"updated_at":"2026-01-01T00:03:00Z"}
            save_snapshot(db,low); save_snapshot(db,high)
            self.assertTrue(latest_alerts(db))

    def test_discovery_provider_failure_is_clear(self):
        with patch.object(engine,"_dex_search",side_effect=RuntimeError("offline")):
            r=engine.scan_opportunities()
        self.assertEqual(r["data_status"],"unavailable")
        self.assertIn("message",r)

    def test_risk_validation(self):
        with self.assertRaises(ValueError):
            engine.risk_calculation({"equity":1000,"risk_pct":1,"entry":100,"stop":100})

if __name__=="__main__": unittest.main()
