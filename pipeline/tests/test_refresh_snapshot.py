import copy
import unittest

from pipeline.refresh_snapshot import refresh


class RefreshSnapshotTests(unittest.TestCase):
    def source(self):
        return {
            "holdings": [{"shares": 42}], "companyReports": [{"summary": {"cash": 123}}],
            "consensus": [{
                "cusip": "099502106", "ticker": "BAH", "company": "Booz Allen",
                "operatingMargin": 9.21, "operatingMarginRating": 5,
                "profitabilityInvestorScore": 6, "opportunityScore": 67,
                "buying": 1, "holders": 1, "scoreStatus": "COMPLETE",
            }],
        }

    def test_booz_allen_regression_and_original_data_preservation(self):
        source = self.source()
        before = copy.deepcopy(source)
        result = refresh(source, [{"id": "numantia"}])
        row = result["consensus"][0]
        self.assertEqual((row["profitabilityInvestorScore"], row["opportunityScore"]), (2, 63))
        self.assertEqual(result["holdings"], before["holdings"])
        self.assertEqual(result["companyReports"], before["companyReports"])
        self.assertEqual(source, before)

    def test_repeated_refresh_does_not_apply_penalty_twice(self):
        first = refresh(self.source(), [])
        second = refresh(first, [])
        self.assertEqual(second["consensus"][0]["opportunityScore"], 63)

    def test_incomplete_score_remains_incomplete(self):
        source = self.source()
        source["consensus"][0].update(operatingMargin=None, opportunityScore=None, scoreStatus="INCOMPLETE")
        result = refresh(source, [])
        self.assertIsNone(result["consensus"][0]["opportunityScore"])
        self.assertEqual(result["consensus"][0]["scoreStatus"], "INCOMPLETE")
