import unittest

from pipeline.build_snapshot import (
    aggregate_holdings, annotate_opportunity_rank_changes, app_safe_company_profiles, build, classify, compact_company_reports, estimate_average_purchase_prices,
    build_public_snapshot_core, consensus_investor_score, debt_to_earnings_investor_score, merge_known, moving_average_investor_score, operating_margin_investor_score,
    quality_investor_score,
    retained_filing_date, valuation_investor_score,
    sanitize_company_profile, yield_investor_score,
    reweight_dividend_growth_score, OPPORTUNITY_SCORE_MAXIMUM,
)


class SnapshotTests(unittest.TestCase):
    def test_dividend_growth_maximum_is_five_without_redistribution(self):
        self.assertEqual([reweight_dividend_growth_score(value) for value in (0, 1, 4, 7, 8)], [0, 1, 3, 4, 5])
        self.assertEqual([reweight_dividend_growth_score(value, 5) for value in range(6)], list(range(6)))
        self.assertEqual(OPPORTUNITY_SCORE_MAXIMUM, 22 + 5 + 35 + 6 + 12 + 7 + 10)
        self.assertEqual(reweight_dividend_growth_score(-1), 0)
        self.assertEqual(reweight_dividend_growth_score(999), 5)
        with self.assertRaises(ValueError):
            reweight_dividend_growth_score(1, 0)

    def test_annotates_opportunity_rank_movement_against_previous_snapshot(self):
        previous = [
            {"company": "Beta Inc", "opportunityScore": 80},
            {"company": "Alpha Inc", "opportunityScore": 75},
            {"company": "Old Inc", "opportunityScore": 70},
            {"company": "Pending Inc", "opportunityScore": None},
        ]
        current = [
            {"company": "Alpha Inc", "opportunityScore": 90},
            {"company": "Beta Inc", "opportunityScore": 85},
            {"company": "New Inc", "opportunityScore": 80},
            {"company": "Pending Inc", "opportunityScore": None},
        ]

        annotate_opportunity_rank_changes(current, previous)

        self.assertEqual((current[0]["opportunityRank"], current[0]["previousOpportunityRank"], current[0]["rankChange"], current[0]["rankStatus"]), (1, 2, 1, "UP"))
        self.assertEqual((current[1]["opportunityRank"], current[1]["previousOpportunityRank"], current[1]["rankChange"], current[1]["rankStatus"]), (2, 1, -1, "DOWN"))
        self.assertEqual((current[2]["opportunityRank"], current[2]["rankChange"], current[2]["rankStatus"]), (3, None, "NEW"))
        self.assertEqual((current[3]["opportunityRank"], current[3]["rankStatus"]), (None, "UNRANKED"))

    def test_company_profiles_always_include_fields_required_by_released_apps(self):
        profile = app_safe_company_profiles([{
            "cusip": "1", "name": "A Co", "tickerResolutionSource": "Verified mapping",
        }])[0]
        self.assertEqual(profile["source"], "Verified mapping")
        self.assertEqual(profile["status"], "identified")
        self.assertTrue(profile["updatedAt"].endswith("Z"))

    def test_non_equity_profile_cannot_keep_equity_metrics(self):
        profile = sanitize_company_profile({
            "cusip": "1", "quoteEligible": False, "marketPrice": 10,
            "dividendYield": 0.08, "peRatio": 12, "paysDividend": True,
        })
        self.assertIsNone(profile["marketPrice"])
        self.assertIsNone(profile["dividendYield"])
        self.assertIsNone(profile["peRatio"])
        self.assertIn("NON_EQUITY_OR_UNQUOTED_INSTRUMENT", profile["metricWarnings"])

    def test_impossible_yield_is_quarantined(self):
        profile = sanitize_company_profile({"cusip": "1", "dividendYield": 1.5})
        self.assertIsNone(profile["dividendYield"])
        self.assertIn("DIVIDEND_YIELD_OUT_OF_RANGE", profile["metricWarnings"])

    def test_missing_qualitative_value_cannot_erase_verified_ticker(self):
        self.assertEqual(merge_known({"ticker": "CPRX"}, {"ticker": None})["ticker"], "CPRX")

    def test_yield_score_changes_gradually(self):
        scores = [yield_investor_score(value) for value in (1, 2, 3, 3.36, 4, 5, 6, 7.5, 9, 10, 12)]
        self.assertEqual(scores, [0, 2, 6, 8, 14, 18, 22, 18, 13, 8, 4])

    def test_pe_score_reserves_perfect_score_for_eight_or_less(self):
        self.assertEqual(valuation_investor_score(8, 18), 35)
        self.assertLess(valuation_investor_score(8.001, 18), 35)
        self.assertEqual(valuation_investor_score(10, 18), 30)
        self.assertEqual(valuation_investor_score(12, 18), 24)
        self.assertLess(valuation_investor_score(17.3, 18), 16)
        self.assertGreater(valuation_investor_score(15, 12), valuation_investor_score(20, 12))
        self.assertGreater(valuation_investor_score(10, 12), valuation_investor_score(30, 12))

    def test_strict_pe_anchors_without_sector_bonuses(self):
        self.assertEqual([valuation_investor_score(pe, 100) for pe in (8, 10, 12, 15, 18, 20, 25, 30, 60)], [35, 30, 24, 16, 10, 7, 2, 0, 0])
        self.assertEqual(valuation_investor_score(15, 100), valuation_investor_score(15, 15))
        self.assertLess(valuation_investor_score(15, 12), valuation_investor_score(15, 15))
        self.assertEqual(valuation_investor_score(11.8, 12), 25)

    def test_pe_score_is_bounded_monotone_and_rejects_invalid_multiples(self):
        for benchmark in (6, 12, 20, 40, 100, 0, None):
            scores = [valuation_investor_score(pe / 100, benchmark) for pe in range(1, 5001)]
            self.assertEqual(scores, sorted(scores, reverse=True))
            self.assertTrue(all(0 <= score <= 35 for score in scores))
        for pe in (None, 0, -5, float('nan'), float('inf'), -float('inf')):
            self.assertEqual(valuation_investor_score(pe, 12), 0)

    def test_consensus_rewards_new_positions_and_penalizes_selling(self):
        established = consensus_investor_score({"holders": 4, "buying": 2, "selling": 0, "newPositions": 0})
        recently_added = consensus_investor_score({"holders": 4, "buying": 2, "selling": 0, "newPositions": 2})
        with_selling = consensus_investor_score({"holders": 4, "buying": 2, "selling": 2, "newPositions": 2})
        self.assertEqual((established, recently_added, with_selling), (5, 7, 5))

    def test_debt_to_earnings_penalizes_high_leverage_gradually(self):
        self.assertEqual(debt_to_earnings_investor_score(0), 10)
        self.assertEqual(debt_to_earnings_investor_score(2), 8)
        self.assertEqual(debt_to_earnings_investor_score(4), 4)
        self.assertEqual(debt_to_earnings_investor_score(6), 0)
        self.assertEqual(debt_to_earnings_investor_score(None, loss_making=True), 0)

    def test_moving_average_score_rewards_prices_below_the_average(self):
        self.assertEqual(moving_average_investor_score(-30), 6)
        self.assertGreater(moving_average_investor_score(-10), moving_average_investor_score(10))
        self.assertEqual(moving_average_investor_score(0), 3)
        self.assertEqual(moving_average_investor_score(40), 0)

    def test_operating_margin_penalizes_weak_margins(self):
        values = (None, -10, 0, 3, 5, 9, 9.21, 10, 15, 20, 25, 30, 60)
        self.assertEqual(
            [operating_margin_investor_score(value) for value in values],
            [0, 0, 0, 0, 0, 2, 2, 2, 4, 6, 8, 10, 10],
        )

    def test_margin_component_keeps_weight_and_booz_allen_gets_two_points(self):
        self.assertEqual(round(operating_margin_investor_score(9.21) * 12 / 10), 2)
        self.assertEqual(round(operating_margin_investor_score(30) * 12 / 10), 12)
        self.assertLess(operating_margin_investor_score(29.99), 10)
        ratings = [operating_margin_investor_score(value / 10) for value in range(-100, 601)]
        self.assertEqual(ratings, sorted(ratings))
        self.assertTrue(all(0 <= rating <= 10 for rating in ratings))

    def test_quality_uses_sector_specific_models_and_explicit_coverage(self):
        general = quality_investor_score({
            "operatingMargin": 22, "roce": 18, "netMargin": 14,
            "cashFromOperations": 120, "netIncome": 100,
        }, "Industrials", "Aerospace")
        financial = quality_investor_score({
            "netMargin": 22, "netIncome": 100, "dividendsPaid": -55,
            "revenue": 300, "expenses": 150,
        }, "Financials", "Bank")
        real_estate = quality_investor_score({
            "operatingMargin": 35, "netMargin": 20, "netIncome": 50,
            "cashFromOperations": 100, "dividendsPaid": -75,
        }, "Real Estate", "REIT")
        self.assertEqual((general["model"], general["coverage"], general["status"]), ("GENERAL", 100, "COMPLETE"))
        self.assertEqual((financial["model"], financial["coverage"], financial["status"]), ("FINANCIAL", 100, "COMPLETE"))
        self.assertEqual((real_estate["model"], real_estate["coverage"], real_estate["status"]), ("REAL_ESTATE", 100, "COMPLETE"))

    def test_public_core_removes_heavy_reports_and_keeps_lazy_manifest(self):
        snapshot = {"companyReports": [
            {"ticker": "ABC", "form": "10-K/A", "filingDate": "2026-01-01", "summary": {"netIncome": 1}},
            {"ticker": "ABC", "form": "10-Q", "filingDate": "2026-05-01", "summary": {"netIncome": 2}},
        ]}
        core, bundles = build_public_snapshot_core(snapshot)
        self.assertEqual(core["companyReports"], [])
        self.assertEqual(core["companyReportFiles"]["ABC"], "company-reports/ABC.json")
        self.assertEqual(len(core["companyReportSummaries"]), 1)
        self.assertEqual(len(bundles["ABC"]), 2)

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

    def test_scores_quoted_company_even_when_no_monitored_fund_holds_it(self):
        current = {"quarter": "2026-Q1", "investors": []}
        profiles = [{
            "cusip": "SP500:1:MO", "ticker": "MO", "name": "Altria",
            "marketPrice": 70, "dividendYield": 0.06, "peRatio": 14,
            "movingAverage1000": 50, "paysDividend": True,
        }]
        result = build(current, {"investors": []}, [], company_profiles=profiles)
        self.assertEqual(result["consensus"], [])
        self.assertEqual(len(result["companyScores"]), 1)
        self.assertEqual(result["companyScores"][0]["ticker"], "MO")
        self.assertIsNotNone(result["companyScores"][0]["opportunityScore"])
        self.assertEqual(result["companyScores"][0]["holders"], 0)

    def test_empty_annual_amendment_does_not_hide_original_report_metrics(self):
        current = {"quarter": "2026-Q1", "investors": []}
        profiles = [{"cusip": "1", "ticker": "MO", "name": "Altria", "marketPrice": 70}]
        reports = [
            {"cusip": "1", "ticker": "MO", "companyName": "Altria", "form": "10-K", "filingDate": "2026-02-01", "reportDate": "2025-12-31", "summary": {"operatingMargin": 42, "netMargin": 30}},
            {"cusip": "1", "ticker": "MO", "companyName": "Altria", "form": "10-K/A", "filingDate": "2026-05-01", "reportDate": "2025-12-31", "summary": {"operatingMargin": None, "netMargin": None}},
        ]
        item = build(current, {"investors": []}, [], company_profiles=profiles, company_reports=reports)["companyScores"][0]
        self.assertEqual(item["operatingMargin"], 42)
        self.assertEqual(item["netMargin"], 30)

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
        self.assertEqual(result["consensus"][0]["dividendInvestorScore"], 10)
        self.assertEqual(result["consensus"][0]["valuationInvestorScore"], 12)
        self.assertEqual(result["consensus"][0]["profitabilityInvestorScore"], 0)
        self.assertIsNotNone(result["consensus"][0]["opportunityScore"])
        self.assertEqual(result["consensus"][0]["scoreStatus"], "PARTIAL")
        self.assertIn("qualityOperatingMargin", result["consensus"][0]["missingScoreMetrics"])
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
        self.assertEqual(item["dividendGrowthInvestorScore"], 5)
        self.assertEqual(item["dividendGrowthScoreMaximum"], 5)
        self.assertEqual(item["opportunityScoreMaximum"], 97)

    def test_derives_market_metrics_and_publishes_score_only_when_complete(self):
        current = {"quarter": "2026-Q1", "investors": [{
            "id": "x", "name": "Manager", "filingDate": "2026-05-15T00:00:00Z",
            "quarterEnd": "2026-03-31T00:00:00Z", "portfolioValue": 1,
            "holdings": [{"ticker": "AAA", "cusip": "1", "company": "Example Inc Class A", "shares": 1, "value": 1}],
        }]}
        profiles = [{
            "cusip": "2", "name": "Example Inc", "marketPrice": 20, "paysDividend": True,
            "movingAverage1000": 25, "priceVsMovingAverage1000Percent": -20,
        }]
        reports = [{
            "cusip": "2", "companyName": "Example Inc", "form": "10-K", "filingDate": "2026-02-01T00:00:00Z",
            "summary": {"operatingMargin": 18, "roce": 22, "epsDiluted": 2, "totalDebt": 60, "cash": 20, "netIncome": 20},
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
        self.assertEqual(item["movingAverageInvestorScore"], 6)
        self.assertEqual(item["debtToEarnings"], 2)
        self.assertEqual(item["debtRatioBasis"], "NET_DEBT_TO_NET_INCOME")
        self.assertEqual(item["leverageInvestorScore"], 8)
        self.assertEqual(item["scoreStatus"], "PARTIAL")
        self.assertIn("qualityNetMargin", item["missingScoreMetrics"])
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
