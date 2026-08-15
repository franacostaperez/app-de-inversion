import unittest

from pipeline.enrich_companies import number, profile_from_overview, select_symbol


class CompanyEnrichmentTests(unittest.TestCase):
    def test_selects_confident_us_equity(self):
        payload = {"bestMatches": [
            {"1. symbol": "ABC.L", "3. type": "Equity", "4. region": "United Kingdom", "9. matchScore": "0.95"},
            {"1. symbol": "ABC", "3. type": "Equity", "4. region": "United States", "9. matchScore": "0.82"},
        ]}
        self.assertEqual(select_symbol(payload, "ABC Corp"), "ABC")

    def test_profile_exposes_dividend_and_market_cap(self):
        profile = profile_from_overview("123456789", "Fallback", "ABC", {
            "Symbol": "ABC", "Name": "ABC Corp", "MarketCapitalization": "1200000",
            "DividendPerShare": "1.20", "DividendYield": "0.03", "PERatio": "12.5", "EPS": "4.2",
        })
        self.assertTrue(profile["paysDividend"])
        self.assertEqual(profile["marketCapitalization"], 1_200_000)
        self.assertEqual(number("None"), None)


if __name__ == "__main__":
    unittest.main()
