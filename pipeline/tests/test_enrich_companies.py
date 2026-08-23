import unittest

from pipeline.enrich_companies import metric, number, profile_from_google


class CompanyEnrichmentTests(unittest.TestCase):
    def test_reads_google_finance_metrics(self):
        page = ('<div class="SwQK7">Dividend</div><div class="dO6ijd">6.25%</div>'
                '<div class="SwQK7">Quarterly dividend</div><div class="dO6ijd">$0.40</div>'
                '<div class="SwQK7">P/E ratio</div><div class="dO6ijd">12.50</div>')
        profile = profile_from_google("123", "Example", "ABC", "NYSE", page)
        self.assertEqual(profile["dividendYield"], 0.0625)
        self.assertEqual(profile["dividendPerShare"], 1.6)
        self.assertEqual(profile["peRatio"], 12.5)
        self.assertEqual(profile["source"], "Google Finance")

    def test_missing_metric_is_none(self):
        self.assertIsNone(metric("<html></html>", "Dividend"))
        self.assertIsNone(number("—"))


if __name__ == "__main__":
    unittest.main()
