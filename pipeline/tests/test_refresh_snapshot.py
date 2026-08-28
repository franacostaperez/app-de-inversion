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
                "pe": 11.8, "sectorPEBenchmark": 12, "valuationInvestorScore": 33,
                "buying": 1, "holders": 1, "scoreStatus": "COMPLETE",
            }],
        }

    def test_booz_allen_regression_and_original_data_preservation(self):
        source = self.source()
        before = copy.deepcopy(source)
        result = refresh(source, [{"id": "numantia"}])
        row = result["consensus"][0]
        self.assertEqual((row["profitabilityInvestorScore"], row["valuationInvestorScore"], row["opportunityScore"]), (2, 25, 55))
        self.assertEqual(result["holdings"], before["holdings"])
        self.assertEqual(result["companyReports"], before["companyReports"])
        self.assertEqual(source, before)

    def test_repeated_refresh_does_not_apply_penalty_twice(self):
        first = refresh(self.source(), [])
        second = refresh(first, [])
        self.assertEqual(second["consensus"][0]["opportunityScore"], 55)

    def test_current_margin_score_is_unchanged_by_valuation_refresh(self):
        source = self.source()
        source["consensus"][0].update(profitabilityInvestorScore=2, operatingMarginRating=2, opportunityScore=63)
        result = refresh(source, [])
        row = result["consensus"][0]
        self.assertEqual((row["profitabilityInvestorScore"], row["valuationInvestorScore"], row["opportunityScore"]), (2, 25, 55))

    def test_missing_and_loss_making_pe_never_gain_valuation_points(self):
        for pe in (None, -4):
            source = self.source()
            source["consensus"][0].update(pe=pe, opportunityScore=None, scoreStatus="INCOMPLETE")
            row = refresh(source, [])["consensus"][0]
            self.assertEqual(row["valuationInvestorScore"], 0)
            self.assertIsNone(row["opportunityScore"])

    def test_incomplete_score_remains_incomplete(self):
        source = self.source()
        source["consensus"][0].update(operatingMargin=None, opportunityScore=None, scoreStatus="INCOMPLETE")
        result = refresh(source, [])
        self.assertIsNone(result["consensus"][0]["opportunityScore"])
        self.assertEqual(result["consensus"][0]["scoreStatus"], "INCOMPLETE")

    def test_growth_reweight_updates_subtotal_total_and_is_idempotent(self):
        source = self.source()
        source["consensus"][0].update(profitabilityInvestorScore=2, operatingMarginRating=2,
                                     valuationInvestorScore=25, opportunityScore=55,
                                     dividendGrowthInvestorScore=8, yieldInvestorScore=7, dividendInvestorScore=15)
        result = refresh(source, [])
        row = result["consensus"][0]
        self.assertEqual((row["dividendGrowthInvestorScore"], row["dividendInvestorScore"], row["opportunityScore"]), (5, 12, 52))
        self.assertEqual((row["dividendGrowthScoreMaximum"], row["opportunityScoreMaximum"]), (5, 97))
        again = refresh(result, [])["consensus"][0]
        self.assertEqual((again["dividendGrowthInvestorScore"], again["opportunityScore"]), (5, 52))

    def test_growth_eligibility_zero_and_incomplete_status_are_preserved(self):
        source = self.source()
        source["consensus"][0].update(dividendGrowthInvestorScore=0, dividendGrowth=10,
                                     yieldInvestorScore=7, dividendInvestorScore=7,
                                     opportunityScore=None, scoreStatus="INCOMPLETE")
        row = refresh(source, [])["consensus"][0]
        self.assertEqual((row["dividendGrowthInvestorScore"], row["dividendInvestorScore"]), (0, 7))
        self.assertIsNone(row["opportunityScore"])
