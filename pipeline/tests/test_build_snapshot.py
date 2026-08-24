import unittest

from pipeline.build_snapshot import (
    aggregate_holdings, build, classify, compact_company_reports, estimate_average_purchase_prices,
    merge_known, operating_margin_investor_score, retained_filing_date, valuation_investor_score,
    yield_investor_score,
)


class SnapshotTests(unittest.TestCase):
    def test_missing_qualitative_value_cannot_erase_verified_ticker(self):
        self.assertEqual(merge_known({"ticker": "CPRX"}, {"ticker": None})["ticker"], "CPRX")

    def test_yield_score_changes_gradually(self):
        scores = [yield_investor_score(value) for value in (1, 2, 3, 3.36, 4, 5, 6, 7.5, 9, 10, 12)]
        self.assertEqual(scores, [0, 2, 6, 7, 13, 17, 21, 18, 13, 8, 5])

    def test_pe_score_reserves_perfect_score_for_ten_or_less(self):
        self.assertEqual(valuation_investor_score(10, 18), 50)
        self.assertLess(valuation_investor_score(12, 18), 50)
        self.assertLess(valuation_investor_score(17.3, 18), 40)
        self.assertGreater(valuation_investor_score(15, 12), valuation_investor_score(20, 12))
        self.assertGreater(valuation_investor_score(10, 12), valuation_investor_score(30, 12))

    def test_operating_margin_uses_exact_ten_point_ladder(self):
        values = (-1, 0, 2.9, 3, 5.9, 6, 8.9, 9, 11.9, 12, 14.9, 15, 19.9, 20, 24.9, 25, 29.9, 30)
        self.assertEqual(
            [operating_margin_investor_score(value) for value in values],
            [1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10],
        )

    def test_non_dividend_company_gets_no_dividend_growth_points(self):
        current = {"quarter": "2026-Q1", "investors": [{
            "id": "x", "name": "Manager", "filingDate": "2026-05-15T00:00:00Z",
            "quarterEnd": "2026-03-31T00:00:00Z", "portfolioValue": 1,
            "holdings": [{"ticker": "PRIVATE", "cusip": "1", "company": "Private Co", "shares": 1, "value": 1}],
        }]}
        profiles = [{"cusip": "1", "name": "Private Co", "paysDividend": False}]
        item = build(current, {"investors": []}, [], company_profiles=profiles)["consensus"][0]
        self.assertEqual(item["yieldInvestorScore"], 0)
        self.assertNotIn("payoutInvestorScore", item)
        self.assertNotIn("payout", item)
        self.assertEqual(item["dividendGrowthInvestorScore"], 0)
        self.assertEqual(item["dividendInvestorScore"], 0)

    def test_compacts_report_metrics_without_losing_annual_history(self):
        annual_old = {
            "cusip": "1", "accessionNumber": "old", "form": "10-K", "filingDate": "2025-02-01",
            "metrics": {"revenue": {"concept": "Revenue", "periods": [{"startDate": "2023-01-01", "endDate": "2023-12-31", "value": 10}]}},
        }
        annual_new = {
            "cusip": "1", "accessionNumber": "new", "form": "10-K", "filingDate": "2026-02-01",
            "metrics": {"revenue": {"concept": "Revenue", "periods": [{"startDate": "2024-01-01", "endDate": "2024-12-31", "value": 12}]}},
        }
        quarter = {"cusip": "1", "accessionNumber": "q", "form": "10-Q", "filingDate": "2026-05-01", "metrics": annual_new["metrics"]}
        result = compact_company_reports([annual_old, annual_new, quarter])
        by_id = {item["accessionNumber"]: item for item in result}
        self.assertEqual(by_id["old"]["metrics"], {})
        self.assertEqual(by_id["q"]["metrics"], {})
        self.assertEqual(len(by_id["new"]["metrics"]["revenue"]["periods"]), 2)

    def test_classification(self):
        self.assertEqual(classify(0, 10), ("NEW", None))
        self.assertEqual(classify(10, 0), ("SOLD", -100.0))
        self.assertEqual(classify(10, 15), ("INCREASED", 50.0))
        self.assertEqual(classify(10, 5), ("REDUCED", -50.0))
        self.assertEqual(classify(10, 10), ("UNCHANGED", 0.0))

    def test_aggregates_duplicate_cusip_rows(self):
        rows = [
            {"ticker": "AAA", "cusip": "000000001", "shares": 10, "value": 20},
            {"ticker": "AAA", "cusip": "000000001", "shares": 5, "value": 8},
        ]
        result = aggregate_holdings(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["shares"], 15)
        self.assertEqual(result[0]["value"], 28)

    def test_estimates_weighted_average_purchase_price(self):
        filings = [
            {"investorId": "x", "reportDate": "2025-03-31", "holdings": [
                {"ticker": "AAA", "cusip": "1", "shares": 10, "value": 100}
            ]},
            {"investorId": "x", "reportDate": "2025-06-30", "holdings": [
                {"ticker": "AAA", "cusip": "1", "shares": 20, "value": 300}
            ]},
            {"investorId": "x", "reportDate": "2025-09-30", "holdings": [
                {"ticker": "AAA", "cusip": "1", "shares": 15, "value": 180}
            ]},
        ]
        result = estimate_average_purchase_prices(filings)
        self.assertEqual(result[("x", "1")], 12.5)

    def test_filters_filing_dates_outside_three_year_window(self):
        from datetime import date
        self.assertTrue(retained_filing_date("2023-08-15T00:00:00Z", date(2026, 8, 15)))
        self.assertFalse(retained_filing_date("2023-08-14T00:00:00Z", date(2026, 8, 15)))

    def test_builds_explainable_score_and_movements(self):
        previous = {"investors": [{"id": "x", "holdings": [{"ticker": "AAA", "cusip": "000000001", "shares": 10}]}]}
        current = {"quarter": "2026-Q1", "investors": [{
            "id": "x", "name": "Manager", "filingDate": "2026-05-15T00:00:00Z",
            "quarterEnd": "2026-03-31T00:00:00Z", "portfolioValue": 1,
            "holdings": [{"ticker": "AAA", "cusip": "000000001", "company": "A Co", "shares": 20, "value": 1}]
        }]}
        companies = [{"ticker": "AAA", "cusip": "000000001", "company": "A Co", "sector": "Tech", "yield": 3, "metricsStatus": "verified",
                      "pe": 15, "dividendGrowth5Y": 4, "debtToEBITDA": 1,
                      "valuationScore": 80, "dividendScore": 80, "qualityScore": 80}]
        result = build(current, previous, companies)
        self.assertEqual(result["movements"][0]["action"], "INCREASED")
        self.assertEqual(result["movements"][0]["previousShares"], 10)
        self.assertEqual(result["movements"][0]["shares"], 20)
        self.assertEqual(result["opportunities"][0]["smartMoneyScore"], 62)
        self.assertEqual(result["opportunities"][0]["franScore"], 76)
        self.assertEqual(result["holdings"][0]["ticker"], "AAA")
        self.assertEqual(result["holdings"][0]["weight"], 100.0)
        self.assertEqual(result["consensus"][0]["cusip"], "000000001")
        self.assertIn("opportunityScore", result["consensus"][0])
        self.assertEqual(result["consensus"][0]["dividendInvestorScore"], 13)
        self.assertEqual(result["consensus"][0]["valuationInvestorScore"], 35)
        self.assertEqual(result["consensus"][0]["profitabilityInvestorScore"], 0)
        self.assertIsNone(result["consensus"][0]["opportunityScore"])
        self.assertEqual(result["consensus"][0]["scoreStatus"], "INCOMPLETE")
        self.assertIn("operatingMargin", result["consensus"][0]["missingScoreMetrics"])
        self.assertNotIn("roce", result["consensus"][0]["missingScoreMetrics"])

    def test_creates_a_filing_news_summary(self):
        previous = {"investors": [{"id": "x", "holdings": []}]}
        current = {
            "quarter": "2026-Q1",
            "filings": [{
                "investorId": "x", "investorName": "Manager", "accessionNumber": "abc",
                "filingDate": "2026-05-15T00:00:00Z", "reportDate": "2026-03-31T00:00:00Z",
                "quarter": "2026-Q1", "secURL": "https://www.sec.gov/example",
            }],
            "investors": [{
                "id": "x", "name": "Manager", "accessionNumber": "abc",
                "filingDate": "2026-05-15T00:00:00Z", "quarterEnd": "2026-03-31T00:00:00Z",
                "portfolioValue": 100, "holdings": [
                    {"ticker": "AAA", "cusip": "1", "company": "A Co", "shares": 10, "value": 100}
                ],
            }],
        }
        result = build(current, previous, [])
        update = result["filingUpdates"][0]
        self.assertEqual(update["newPositions"], 1)
        self.assertIn("A Co", update["summary"])

    def test_rewards_consistent_dividend_growth(self):
        current = {"quarter": "2026-Q1", "investors": [{
            "id": "x", "name": "Manager", "filingDate": "2026-05-15T00:00:00Z",
            "quarterEnd": "2026-03-31T00:00:00Z", "portfolioValue": 1,
            "holdings": [{"ticker": "AAA", "cusip": "1", "company": "A Co", "shares": 1, "value": 1}],
        }]}
        companies = [{"ticker": "AAA", "cusip": "1", "company": "A Co", "yield": 4, "pe": 15}]
        reports = [{
            "cusip": "1", "form": "10-K", "filingDate": "2026-02-01T00:00:00Z",
            "summary": {"operatingMargin": 20},
            "metrics": {"dividendPerShare": {"periods": [
                {"endDate": "2023-12-31", "fiscalPeriod": "FY", "value": 1.0},
                {"endDate": "2024-12-31", "fiscalPeriod": "FY", "value": 1.1},
                {"endDate": "2025-12-31", "fiscalPeriod": "FY", "value": 1.21},
            ]}},
        }]
        item = build(current, {"investors": []}, companies, company_reports=reports)["consensus"][0]
        self.assertEqual(item["dividendGrowth"], 10)
        self.assertEqual(item["dividendGrowthInvestorScore"], 9)

    def test_derives_market_metrics_and_publishes_score_only_when_complete(self):
        current = {"quarter": "2026-Q1", "investors": [{
            "id": "x", "name": "Manager", "filingDate": "2026-05-15T00:00:00Z",
            "quarterEnd": "2026-03-31T00:00:00Z", "portfolioValue": 1,
            "holdings": [{"ticker": "AAA", "cusip": "1", "company": "Example Inc Class A", "shares": 1, "value": 1}],
        }]}
        profiles = [{"cusip": "2", "name": "Example Inc", "marketPrice": 20, "paysDividend": True}]
        reports = [{
            "cusip": "2", "companyName": "Example Inc", "form": "10-K", "filingDate": "2026-02-01T00:00:00Z",
            "summary": {"operatingMargin": 18, "roce": 22, "epsDiluted": 2},
            "metrics": {"dividendPerShare": {"periods": [
                {"endDate": "2024-12-31", "fiscalPeriod": "FY", "value": 0.8},
                {"endDate": "2025-12-31", "fiscalPeriod": "FY", "value": 1.0},
            ]}},
        }]
        item = build(current, {"investors": []}, [], company_profiles=profiles, company_reports=reports)["consensus"][0]
        self.assertEqual(item["pe"], 10)
        self.assertEqual(item["yield"], 5)
        self.assertEqual(item["earningsPerShare"], 2)
        self.assertEqual(item["peCalculation"], "PRICE_OVER_ANNUAL_DILUTED_EPS")
        self.assertEqual(item["scoreStatus"], "COMPLETE")
        self.assertEqual(item["missingScoreMetrics"], [])
        self.assertIsNotNone(item["opportunityScore"])

    def test_consolidates_share_classes_without_counting_a_fund_twice(self):
        current = {"quarter": "2026-Q1", "investors": [{
            "id": "x", "name": "Manager", "filingDate": "2026-05-15T00:00:00Z",
            "quarterEnd": "2026-03-31T00:00:00Z", "portfolioValue": 2,
            "holdings": [
                {"ticker": "AAA", "cusip": "1", "company": "Example Inc", "shares": 1, "value": 1},
                {"ticker": "AAB", "cusip": "2", "company": "Example Inc", "shares": 1, "value": 1},
            ],
        }]}
        items = build(current, {"investors": []}, [])["consensus"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["holders"], 1)
        self.assertEqual(items[0]["buying"], 1)

    def test_sorts_funds_by_portfolio_value(self):
        current = {"quarter": "2026-Q1", "investors": [
            {"id": "small", "name": "Small", "filingDate": "2026-05-15T00:00:00Z", "quarterEnd": "2026-03-31T00:00:00Z", "portfolioValue": 10, "holdings": []},
            {"id": "large", "name": "Large", "filingDate": "2026-05-15T00:00:00Z", "quarterEnd": "2026-03-31T00:00:00Z", "portfolioValue": 100, "holdings": []},
        ]}
        result = build(current, {"investors": []}, [])
        self.assertEqual([item["id"] for item in result["investors"]], ["large", "small"])

    def test_removes_news_for_funds_no_longer_monitored(self):
        current = {"quarter": "2026-Q1", "investors": []}
        old_update = {
            "investorId": "removed", "accessionNumber": "old", "filingDate": "2026-05-15T00:00:00Z"
        }
        result = build(current, {"investors": []}, [], prior_updates=[old_update])
        self.assertEqual(result["filingUpdates"], [])


if __name__ == "__main__":
    unittest.main()
