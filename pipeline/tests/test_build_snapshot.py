import unittest

from pipeline.build_snapshot import aggregate_holdings, build, classify, retained_filing_date


class SnapshotTests(unittest.TestCase):
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
        companies = [{"ticker": "AAA", "company": "A Co", "sector": "Tech", "yield": 3, "metricsStatus": "verified",
                      "pe": 15, "payout": 50, "dividendGrowth5Y": 4, "debtToEBITDA": 1,
                      "valuationScore": 80, "dividendScore": 80, "qualityScore": 80}]
        result = build(current, previous, companies)
        self.assertEqual(result["movements"][0]["action"], "INCREASED")
        self.assertEqual(result["movements"][0]["previousShares"], 10)
        self.assertEqual(result["movements"][0]["shares"], 20)
        self.assertEqual(result["opportunities"][0]["smartMoneyScore"], 62)
        self.assertEqual(result["opportunities"][0]["franScore"], 76)
        self.assertEqual(result["holdings"][0]["ticker"], "AAA")
        self.assertEqual(result["holdings"][0]["weight"], 100.0)

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


if __name__ == "__main__":
    unittest.main()
