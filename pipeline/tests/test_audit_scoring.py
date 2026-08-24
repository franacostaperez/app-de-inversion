import unittest

from pipeline.audit_scoring import build_audit


class ScoringAuditTests(unittest.TestCase):
    def test_reports_missing_metrics_by_company(self):
        audit = build_audit({"generatedAt": "now", "companyProfiles": [{"cusip": "2", "ticker": "PND"}], "consensus": [
            {"company": "Complete", "opportunityScore": 80},
            {"company": "Pending", "cusip": "2", "opportunityScore": None, "scoreCoverage": 60,
             "missingScoreMetrics": ["pe", "roce"], "yield": 4},
        ]})
        self.assertEqual(audit["companiesWithCompleteScore"], 1)
        self.assertEqual(audit["missingByMetric"], {"pe": 1, "roce": 1})
        self.assertEqual(audit["companies"][0]["company"], "Pending")
        self.assertEqual(audit["blockingCategories"], {"VERIFIED_TICKER_MISSING_METRICS": 1})


if __name__ == "__main__":
    unittest.main()
