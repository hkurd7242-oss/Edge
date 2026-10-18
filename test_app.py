import unittest
from app import app
from engine import risk_calculation

class AppTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_health(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json["ok"])

    def test_risk_calculation(self):
        r = risk_calculation({"equity":10000,"risk_pct":0.5,"entry":100,"stop":95,"cost_pct":0.2})
        self.assertAlmostEqual(r["risk_budget"],50)
        self.assertGreater(r["quantity"],0)

    def test_risk_rejects_bad_prices(self):
        with self.assertRaises(ValueError):
            risk_calculation({"equity":10000,"risk_pct":0.5,"entry":100,"stop":100,"cost_pct":0})

    def test_unknown_asset_is_explicit(self):
        r = self.client.get("/api/analyze/NOTAREALCOIN")
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json["status"],"not_found_in_initial_universe")

if __name__ == "__main__":
    unittest.main()
