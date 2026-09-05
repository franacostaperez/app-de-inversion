import unittest

from pipeline.yahoo_company_reports import extract_dividend_series, extract_series, reports_for_profile, summary_on


class YahooCompanyReportsTests(unittest.TestCase):
    def payload(self):
        def series(key, rows):
            return {key: [
                {"asOfDate": day, "periodType": "12M", "currencyCode": "GBP", "reportedValue": {"raw": value}}
                for day, value in rows
            ]}
        return {"timeseries": {"result": [
            series("annualTotalRevenue", [("2024-12-31", 100), ("2025-12-31", 120)]),
            series("annualOperatingIncome", [("2024-12-31", 20), ("2025-12-31", 30)]),
            series("annualNetIncome", [("2024-12-31", 10), ("2025-12-31", 18)]),
            series("annualOperatingCashFlow", [("2024-12-31", 14), ("2025-12-31", 22)]),
            series("annualTotalDebt", [("2024-12-31", 40), ("2025-12-31", 35)]),
            series("annualInvestedCapital", [("2024-12-31", 80), ("2025-12-31", 100)]),
            series("annualCashDividendsPaid", [("2024-12-31", -4), ("2025-12-31", -5)]),
        ]}}

    def test_extracts_and_normalizes_annual_metrics(self):
        metrics = extract_series(self.payload())
        self.assertEqual(metrics["revenue"]["periods"][-1]["value"], 120)
        self.assertEqual(metrics["dividendsPaid"]["periods"][-1]["value"], 5)
        summary = summary_on(metrics, "2025-12-31")
        self.assertEqual(summary["operatingMargin"], 25)
        self.assertEqual(summary["netMargin"], 15)
        self.assertEqual(summary["roce"], 30)

    def test_builds_one_scored_report_per_year(self):
        dividends = {"chart": {"result": [{
            "meta": {"currency": "GBP"},
            "events": {"dividends": {
                "a": {"date": 1735603200, "amount": 0.4},
                "b": {"date": 1767139200, "amount": 0.5},
            }},
        }]}}
        reports = reports_for_profile(
            {"cusip": "FTSE100:TST", "ticker": "TST.L", "name": "Test plc"},
            self.payload(), dividends,
        )
        self.assertEqual(len(reports), 2)
        self.assertEqual(reports[-1]["form"], "ANNUAL")
        self.assertTrue(reports[-1]["metrics"])
        self.assertEqual(len(reports[-1]["metrics"]["dividendPerShare"]["periods"]), 2)
        self.assertFalse(reports[0]["metrics"])
        self.assertIn("+20.0%", reports[-1]["highlights"][0])

    def test_extracts_calendar_year_dividend_history(self):
        payload = {"chart": {"result": [{
            "meta": {"currency": "GBP"},
            "events": {"dividends": {
                "a": {"date": 1704067200, "amount": 0.4},
                "b": {"date": 1719792000, "amount": 0.6},
            }},
        }]}}
        metric = extract_dividend_series(payload)
        self.assertEqual(metric["periods"][0]["value"], 1.0)
        self.assertEqual(metric["periods"][0]["unit"], "GBP")

    def test_no_dividend_events_is_not_a_synthetic_history(self):
        payload = {"chart": {"result": [{"meta": {"currency": "GBP"}, "events": {}}]}}
        self.assertIsNone(extract_dividend_series(payload))


if __name__ == "__main__":
    unittest.main()
