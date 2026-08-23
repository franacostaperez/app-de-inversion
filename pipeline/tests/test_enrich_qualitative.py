import unittest

from pipeline.enrich_qualitative import fallback_profile


class QualitativeEnrichmentTests(unittest.TestCase):
    def test_builds_cautious_complete_profile(self):
        result = fallback_profile(
            {"cusip": "1", "company": "Example Inc"},
            {"ticker": "EX", "sector": "Technology", "industry": "Software"},
        )
        self.assertEqual(result["ticker"], "EX")
        self.assertIn("Software", result["description"])
        self.assertTrue(result["businessModel"])
        self.assertTrue(result["revenueModel"])
        self.assertTrue(result["economicMoat"])


if __name__ == "__main__":
    unittest.main()
