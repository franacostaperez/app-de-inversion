import unittest

from pipeline.enrich_qualitative import fallback_profile, inferred_sector


class QualitativeEnrichmentTests(unittest.TestCase):
    def test_builds_cautious_complete_profile(self):
        result = fallback_profile(
            {"cusip": "1", "company": "Example Inc"},
            {"ticker": "EX", "sector": "Technology", "industry": "Software"},
        )
        self.assertEqual(result["ticker"], "EX")
        self.assertIn("software", result["description"])
        self.assertTrue(result["businessModel"])
        self.assertTrue(result["revenueModel"])
        self.assertTrue(result["economicMoat"])
        self.assertIn("Ventajas competitivas potenciales", result["economicMoat"])
        self.assertIn("retener clientes", result["businessModel"])

    def test_uses_sec_industry_to_build_a_specific_activity_profile(self):
        result = fallback_profile(
            {"cusip": "1", "company": "Example Bank"},
            {"ticker": "EX", "industry": "STATE COMMERCIAL BANKS"},
        )
        self.assertEqual(inferred_sector(None, "STATE COMMERCIAL BANKS"), "Financials")
        self.assertIn("state commercial banks", result["description"])
        self.assertIn("margen de intereses", result["revenueModel"])


if __name__ == "__main__":
    unittest.main()
