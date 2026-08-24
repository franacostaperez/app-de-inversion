import unittest
import urllib.error

from pipeline.enrich_companies import enrich, metric, number, profile_from_google, validate_market_metrics


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

    def test_reads_current_google_finance_markup(self):
        page = ('<div class="mfs7Fc">P/E ratio</div><div class="tip">Help</div>'
                '<div class="P6K39c">12.75</div>'
                '<div class="mfs7Fc">Dividend yield</div><span>Help</span>'
                '<div class="P6K39c">4.25%</div>')
        profile = profile_from_google("123", "Example", "ABC", "NYSE", page)
        self.assertEqual(profile["peRatio"], 12.75)
        self.assertEqual(profile["dividendYield"], 0.0425)

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

    def test_does_not_quote_delisted_or_debt_instruments(self):
        class Client:
            def google_quote(self, ticker, preferred_exchange=None):
                raise AssertionError("An ineligible instrument must not request a quote")

        catalog = [{"cusip": "123", "ticker": "OLD", "quoteEligible": False,
                    "listingStatus": "DELISTED_ACQUIRED"}]
        result = enrich([{"cusip": "123", "company": "Old Company"}], catalog, Client(), 0)
        self.assertFalse(result[0]["quoteEligible"])

    def test_uses_yahoo_chart_as_market_price_fallback(self):
        from pipeline.enrich_companies import MarketDataClient

        class Client(MarketDataClient):
            def request(self, url, payload=None):
                if "quoteSummary" in url:
                    raise urllib.error.HTTPError(url, 429, "Throttled", None, None)
                return '{"chart":{"result":[{"meta":{"regularMarketPrice":123.45}}]}}'

        profile = Client().yahoo_profile("ABC")
        self.assertEqual(profile["marketPrice"], 123.45)

    def test_calculates_exact_one_thousand_session_average(self):
        import json
        from pipeline.enrich_companies import MarketDataClient

        class Client(MarketDataClient):
            def request(self, url, payload=None):
                closes = list(range(1, 1002))
                return json.dumps({"chart": {"result": [{
                    "meta": {"regularMarketPrice": 1001},
                    "timestamp": list(range(1002)),
                    "indicators": {"adjclose": [{"adjclose": closes}]},
                }]}})

        metrics = Client().yahoo_history_metrics("ABC")
        self.assertEqual(metrics["movingAverage1000Sessions"], 1000)
        self.assertAlmostEqual(metrics["movingAverage1000"], 501.5)
        self.assertAlmostEqual(metrics["priceVsMovingAverage1000Percent"], 99.6)

    def test_does_not_label_short_history_as_a_thousand_session_average(self):
        import json
        from pipeline.enrich_companies import MarketDataClient

        class Client(MarketDataClient):
            def request(self, url, payload=None):
                return json.dumps({"chart": {"result": [{
                    "meta": {"regularMarketPrice": 42},
                    "indicators": {"adjclose": [{"adjclose": [40, 41, 42]}]},
                }]}})

        metrics = Client().yahoo_history_metrics("NEW")
        self.assertEqual(metrics["marketPrice"], 42)
        self.assertNotIn("movingAverage1000", metrics)

    def test_normalizes_percent_yield_and_quarantines_provider_conflict(self):
        normalized = validate_market_metrics({"yahooDividendYield": 4.2, "marketPrice": 100})
        self.assertEqual(normalized["dividendYield"], 0.042)
        conflicted = validate_market_metrics({
            "googleDividendYield": 0.03, "yahooDividendYield": 0.09, "marketPrice": 100,
        })
        self.assertIsNone(conflicted["dividendYield"])
        self.assertIn("MARKET_YIELD_PROVIDER_CONFLICT", conflicted["metricWarnings"])


if __name__ == "__main__":
    unittest.main()
