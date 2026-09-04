import unittest
import urllib.error

from pipeline.enrich_companies import enrich, google_description, metric, number, portfolio_holdings, profile_from_google, validate_market_metrics


class CompanyEnrichmentTests(unittest.TestCase):
    def test_manual_portfolio_company_becomes_an_enrichment_candidate(self):
        positions = [{"ticker": "ABC", "name": "Example", "exchange": "NYSE"}]
        result = portfolio_holdings(positions, [])
        self.assertEqual(result, [{
            "cusip": "PORTFOLIO:ABC", "ticker": "ABC", "company": "Example",
            "exchange": "NYSE", "value": -1,
        }])

    def test_manual_company_reuses_verified_catalog_identity(self):
        positions = [{"ticker": "ABC", "name": "Example"}]
        result = portfolio_holdings(positions, [{"ticker": "ABC", "cusip": "123"}])
        self.assertEqual(result[0]["cusip"], "123")

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

    def test_reads_spanish_metrics_and_company_description(self):
        page = ('<div class="SwQK7">Dividendo</div><div class="dO6ijd">3,75 %</div>'
                '<div class="SwQK7">Dividendo trimestral</div><div class="dO6ijd">0,50 $</div>'
                '<div class="SwQK7">Ratio PER</div><div class="dO6ijd">14,25</div>'
                '<div class="RaUwRb"><div><span>Example fabrica equipos industriales y presta servicios de mantenimiento recurrentes.</span></div>')
        profile = profile_from_google("123", "Example", "ABC", "NYSE", page)
        self.assertEqual(profile["dividendYield"], 0.0375)
        self.assertEqual(profile["dividendPerShare"], 2.0)
        self.assertEqual(profile["peRatio"], 14.25)
        self.assertEqual(profile["description"], google_description(page))
        self.assertIn("equipos industriales", profile["description"])

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

    def test_refreshes_known_catalog_companies_even_without_current_holding(self):
        class Client:
            def google_quote(self, ticker, preferred_exchange=None):
                return None, None
            def yahoo_profile(self, ticker):
                return {}
            def sec_reports(self, ticker):
                return {"industry": "INDUSTRIAL MACHINERY & EQUIPMENT"}

        result = enrich([], [{"cusip": "123", "ticker": "ABC", "name": "Archived Company"}], Client(), 0)
        self.assertEqual(result[0]["industry"], "INDUSTRIAL MACHINERY & EQUIPMENT")

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

    def test_reads_market_cap_and_pe_from_public_yahoo_time_series(self):
        import json
        from pipeline.enrich_companies import MarketDataClient

        class Client(MarketDataClient):
            def request(self, url, payload=None):
                return json.dumps({"timeseries": {"result": [
                    {"trailingMarketCap": [{"reportedValue": {"raw": 12300000000}}]},
                    {"trailingPeRatio": [{"reportedValue": {"raw": 18.75}}]},
                ]}})

        metrics = Client().yahoo_fundamental_metrics("ABC")
        self.assertEqual(metrics["marketCapitalization"], 12300000000)
        self.assertEqual(metrics["peRatio"], 18.75)
        self.assertEqual(metrics["yahooPeRatio"], 18.75)

    def test_live_yahoo_price_replaces_a_stale_price_from_a_previous_ticker(self):
        class Client:
            def google_quote(self, ticker, preferred_exchange=None):
                return None, None

            def yahoo_profile(self, ticker):
                return {
                    "marketPrice": 200, "movingAverage1000": 100,
                    "priceVsMovingAverage1000Percent": 100,
                }

            def sec_reports(self, ticker):
                return {}

        result = enrich(
            [{"cusip": "1", "company": "Company", "ticker": "NEW", "value": 1}],
            [{"cusip": "1", "name": "Company", "ticker": "NEW", "marketPrice": 25}],
            Client(), 0,
        )
        self.assertEqual(result[0]["marketPrice"], 200)
        self.assertEqual(result[0]["priceVsMovingAverage1000Percent"], 100)

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

    def test_derives_trailing_dividend_and_yield_from_chart_events(self):
        import json
        from pipeline.enrich_companies import MarketDataClient

        class Client(MarketDataClient):
            def request(self, url, payload=None):
                return json.dumps({"chart": {"result": [{
                    "meta": {
                        "regularMarketPrice": 100,
                        "regularMarketTime": 2_000_000_000,
                        "currency": "USD",
                        "exchangeName": "NYQ",
                    },
                    "timestamp": list(range(1002)),
                    "events": {"dividends": {
                        "1": {"date": 1_990_000_000, "amount": 1.0},
                        "2": {"date": 1_980_000_000, "amount": 1.0},
                        "old": {"date": 1_900_000_000, "amount": 9.0},
                    }},
                    "indicators": {"adjclose": [{"adjclose": list(range(1, 1002))}]},
                }]}})

        metrics = Client().yahoo_history_metrics("ABC")
        self.assertEqual(metrics["dividendPerShare"], 2.0)
        self.assertEqual(metrics["yahooDividendYield"], 0.02)
        self.assertEqual(metrics["exchange"], "NYSE")

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
        self.assertTrue(metrics["_movingAverage1000Unavailable"])

    def test_short_history_removes_a_stale_moving_average(self):
        class Client:
            def google_quote(self, ticker, preferred_exchange=None):
                return None, None

            def yahoo_profile(self, ticker):
                return {"marketPrice": 200, "_movingAverage1000Unavailable": True}

            def sec_reports(self, ticker):
                return {}

        result = enrich(
            [{"cusip": "1", "company": "Recent IPO", "ticker": "IPO", "value": 1}],
            [{"cusip": "1", "name": "Recent IPO", "ticker": "IPO", "marketPrice": 25,
              "movingAverage1000": 20, "priceVsMovingAverage1000Percent": 25,
              "movingAverage1000Sessions": 1000}],
            Client(), 0,
        )
        self.assertEqual(result[0]["marketPrice"], 200)
        self.assertNotIn("movingAverage1000", result[0])

    def test_normalizes_percent_yield_and_quarantines_provider_conflict(self):
        normalized = validate_market_metrics({"yahooDividendYield": 4.2, "marketPrice": 100})
        self.assertEqual(normalized["dividendYield"], 0.042)
        conflicted = validate_market_metrics({
            "googleDividendYield": 0.03, "yahooDividendYield": 0.09, "marketPrice": 100,
        })
        self.assertIsNone(conflicted["dividendYield"])
        self.assertIn("MARKET_YIELD_PROVIDER_CONFLICT", conflicted["metricWarnings"])

    def test_resolves_yield_conflict_with_verified_annual_dividend_rate(self):
        resolved = validate_market_metrics({
            "googleDividendYield": 0.0346,
            "yahooDividendYield": 0.0173,
            "marketPrice": 188.06,
            "dividendPerShare": 6.52,
        })
        self.assertEqual(resolved["dividendYield"], 0.0346)
        self.assertIn(
            "MARKET_YIELD_CONFLICT_RESOLVED_BY_DIVIDEND_RATE",
            resolved["metricWarnings"],
        )

    def test_resolves_pe_conflict_with_price_over_positive_eps(self):
        resolved = validate_market_metrics({
            "googlePeRatio": 20,
            "yahooPeRatio": 50,
            "marketPrice": 120,
            "eps": 4,
        })
        self.assertEqual(resolved["peRatio"], 30)
        self.assertIn(
            "MARKET_PE_CONFLICT_RESOLVED_BY_PRICE_OVER_EPS",
            resolved["metricWarnings"],
        )


if __name__ == "__main__":
    unittest.main()
