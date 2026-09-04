import unittest

from pipeline.audit_metric_values import build_metric_audit


class MetricValueAuditTests(unittest.TestCase):
    def test_current_score_maximum_includes_solvency(self):
        audit = build_metric_audit({"consensus": [{
            "company": "Complete", "opportunityScore": 97, "opportunityScoreMaximum": 97,
            "dividendInvestorScore": 27, "valuationInvestorScore": 35,
            "movingAverageInvestorScore": 6, "profitabilityInvestorScore": 12,
            "consensusInvestorScore": 7, "leverageInvestorScore": 10,
        }]})
        self.assertNotIn("SCORE_COMPONENTS_DO_NOT_SUM", audit["issuesByCode"])

    def test_audits_full_company_score_universe_and_accepts_handled_conflicts(self):
        audit = build_metric_audit({
            "companyProfiles": [{
                "cusip": "1", "ticker": "ONE", "googlePeRatio": 10, "yahooPeRatio": 30,
                "peRatio": None, "metricWarnings": ["MARKET_PE_PROVIDER_CONFLICT"],
            }],
            "consensus": [],
            "companyScores": [{"cusip": "1", "company": "One", "opportunityScore": None}],
        })
        self.assertEqual(audit["scoresAudited"], 1)
        self.assertNotIn("PE_PROVIDER_CONFLICT", audit["issuesByCode"])

    def test_detects_yield_instrument_margin_and_score_errors(self):
        audit = build_metric_audit({
            "generatedAt": "now",
            "companyProfiles": [{
                "cusip": "1", "name": "Debt", "ticker": "BAD", "quoteEligible": False,
                "marketPrice": 25, "dividendYield": 0.15,
            }, {
                "cusip": "2", "name": "Yield conflict", "ticker": "YLD", "quoteEligible": True,
                "googleDividendYield": 0.04, "yahooDividendYield": 0.08,
            }],
            "consensus": [{
                "cusip": "3", "company": "Margin", "operatingMargin": 250,
                "opportunityScore": 80, "dividendInvestorScore": 20,
                "valuationInvestorScore": 30, "profitabilityInvestorScore": 10,
                "consensusInvestorScore": 1,
            }],
        })
        self.assertEqual(audit["profilesAudited"], 2)
        self.assertIn("NON_EQUITY_HAS_MARKET_METRICS", audit["issuesByCode"])
        self.assertIn("YIELD_PROVIDER_CONFLICT", audit["issuesByCode"])
        self.assertIn("OPERATING_MARGIN_OUT_OF_RANGE", audit["issuesByCode"])
        self.assertIn("SCORE_COMPONENTS_DO_NOT_SUM", audit["issuesByCode"])

    def test_accepts_consistent_metrics(self):
        audit = build_metric_audit({
            "companyProfiles": [{
                "cusip": "1", "name": "Good", "ticker": "GOOD", "quoteEligible": True,
                "marketPrice": 100, "dividendPerShare": 4, "dividendYield": 0.04,
                "googleDividendYield": 0.04, "yahooDividendYield": 0.041,
                "movingAverage1000": 80, "priceVsMovingAverage1000Percent": 25,
            }],
            "consensus": [{
                "cusip": "1", "company": "Good", "operatingMargin": 20,
                "opportunityScore": 70, "dividendInvestorScore": 20,
                "valuationInvestorScore": 30, "profitabilityInvestorScore": 10,
                "consensusInvestorScore": 5, "movingAverageInvestorScore": 5,
            }],
        })
        self.assertEqual(audit["issuesRemaining"], 0)


if __name__ == "__main__":
    unittest.main()
