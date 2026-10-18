import unittest
from unittest.mock import patch
import engine

class MarketScreenTests(unittest.TestCase):
    def test_limit_is_clamped(self):
        with patch.dict("os.environ", {"EDGE_MARKET_LIMIT":"9999"}):
            self.assertEqual(engine._market_limit(), 250)
        with patch.dict("os.environ", {"EDGE_MARKET_LIMIT":"2"}):
            self.assertEqual(engine._market_limit(), 10)
        with patch.dict("os.environ", {"EDGE_MARKET_LIMIT":"invalid"}):
            self.assertEqual(engine._market_limit(), 100)

    def test_score_has_transparent_reasons(self):
        item = engine._score_market_coin({"id":"x","symbol":"X","name":"Example",
            "current_price":1,"price_change_percentage_24h":4,"total_volume":20,
            "market_cap":100,"market_cap_rank":5})
        self.assertEqual(item["score"], 50)
        self.assertEqual(item["action_state"], "research_only")
        self.assertIn("not a probability", item["methodology"])

    def test_provider_failure_is_marked_demo(self):
        with patch.object(engine, "_cg", side_effect=RuntimeError("offline")):
            items = engine.scan_crypto()
        self.assertTrue(items)
        self.assertTrue(all(i["data_status"]=="demo_fallback" for i in items))
        self.assertTrue(all(i["score"] is None for i in items))

    def test_asset_search_failure_is_unverified(self):
        with patch.object(engine, "_cg", side_effect=RuntimeError("offline")):
            result = engine.analyze_asset("SOMECOIN")
        self.assertEqual(result["status"], "not_found")
        self.assertEqual(result["action_state"], "unverified")

if __name__ == "__main__":
    unittest.main()
