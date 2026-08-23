import unittest
import urllib.error

from pipeline.enrich_companies import enrich, metric, number, profile_from_google


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

    def test_daily_refresh_preserves_qualitative_research(self):
        class Client:
            def google_quote(self, ticker, preferred_exchange=None):
                return "NYSE", '<div class="SwQK7">Dividend</div><div class="dO6ijd">4.20%</div>'
            def sec_reports(self, ticker):
                return {}

        catalog = [{"cusip": "123", "ticker": "ABC", "exchange": "NYSE",
                    "businessModel": "Modelo", "revenueModel": "Ingresos", "economicMoat": "Foso"}]
        result = enrich([{"cusip": "123", "company": "ABC"}], catalog, Client(), 0)
        self.assertEqual(result[0]["businessModel"], "Modelo")
        self.assertEqual(result[0]["economicMoat"], "Foso")

    def test_google_404_does_not_stop_other_exchanges(self):
        from pipeline.enrich_companies import MarketDataClient

        class Client(MarketDataClient):
            def request(self, url, payload=None):
                if "NASDAQ" in url:
                    raise urllib.error.HTTPError(url, 404, "Not found", None, None)
                return '<div class="SwQK7">P/E ratio</div><div class="dO6ijd">15.0</div>'

        exchange, page = Client().google_quote("ABC")
        self.assertEqual(exchange, "NYSE")
        self.assertIn("P/E ratio", page)


if __name__ == "__main__":
    unittest.main()
