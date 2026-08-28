import copy
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.build_snapshot import load_fund_portfolios


ROOT = Path(__file__).resolve().parents[2]


class FundPortfolioTests(unittest.TestCase):
    def report(self):
        return json.loads((ROOT / "data/fund-portfolios/numantia/2026-H1.json").read_text())

    def load(self, report):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder) / "numantia"
            directory.mkdir()
            (directory / "report.json").write_text(json.dumps(report))
            return load_fund_portfolios(Path(folder))[0]

    def test_official_numantia_totals_and_dates(self):
        result = self.load(self.report())
        self.assertEqual(result["positionCount"], 27)
        self.assertEqual(result["newPositions"], 9)
        self.assertEqual(result["closedPositions"], 10)
        self.assertEqual(result["netAssets"], 324091000)
        self.assertEqual(sum(row["value"] for row in result["positions"]), 316149000)
        self.assertEqual(result["currency"], "EUR")
        self.assertEqual(result["reportDate"], "2026-06-30T00:00:00Z")
        self.assertIsNone(result["publicationDate"])

    def test_value_growth_is_not_misrepresented_as_share_purchases(self):
        result = self.load(self.report())
        rows = {row["isin"]: row for row in result["positions"]}
        self.assertEqual(rows["US30292L1070"]["status"], "HELD")
        self.assertEqual(rows["US76169C1009"]["status"], "NEW")
        self.assertEqual(rows["US98978V1035"]["status"], "CLOSED")
        self.assertTrue(all(row["shares"] is None for row in rows.values()))
        self.assertTrue(all(row["estimatedAveragePurchasePrice"] is None for row in rows.values()))

    def test_weights_use_total_net_assets_not_only_equities(self):
        result = self.load(self.report())
        self.assertEqual(result["positions"][0]["weight"], 7.61)
        self.assertAlmostEqual(sum(row["weight"] for row in result["positions"]), 97.56, delta=0.03)

    def test_rejects_duplicate_instruments_and_unreconciled_values(self):
        source = self.report()
        source["positions"].append(copy.deepcopy(source["positions"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate ISIN"):
            self.load(source)
        source = self.report()
        source["positions"][0]["value"] *= 1000
        with self.assertRaisesRegex(ValueError, "Unreconciled"):
            self.load(source)

    def test_ttm_yield_strict_threshold_and_negative_pe(self):
        source = self.report()
        source["positions"][0]["metrics"] = {
            "price": 100, "dividendTTM": 3, "peTrailing": -2, "peForward": None,
        }
        row = next(row for row in self.load(source)["positions"] if row["isin"] == source["positions"][0]["isin"])
        self.assertEqual(row["metrics"]["yieldTTM"], 3)
        self.assertFalse(row["metrics"]["yieldAbove3"])
        self.assertIsNone(row["metrics"]["peTrailing"])
        self.assertEqual(row["metrics"]["peTrailingStatus"], "N/M")
        source["positions"][0]["metrics"]["dividendTTM"] = None
        row = next(row for row in self.load(source)["positions"] if row["isin"] == source["positions"][0]["isin"])
        self.assertIsNone(row["metrics"]["yieldTTM"])
        self.assertIsNone(row["metrics"]["yieldAbove3"])

    def test_empty_directory_is_backward_compatible(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(load_fund_portfolios(Path(folder)), [])

    def test_verified_market_metrics_and_missing_data(self):
        result = self.load(self.report())
        rows = {row.get("ticker"): row for row in result["positions"] if row["value"] > 0}
        self.assertEqual(len(rows), 27)
        for row in rows.values():
            metrics = row["metrics"]
            self.assertTrue(metrics["sources"])
            self.assertTrue(metrics["priceDate"])
            self.assertEqual(metrics["consultedAt"], "2026-08-28T00:00:00Z")
            if metrics["dividendTTM"] is not None:
                self.assertAlmostEqual(sum(payment["amount"] for payment in metrics["dividendPayments"]), metrics["dividendTTM"])
                self.assertAlmostEqual(metrics["yieldTTM"], metrics["dividendTTM"] / metrics["price"] * 100)
        self.assertEqual(rows["TSLA"]["metrics"]["yieldTTM"], 0)
        self.assertIsNone(rows["AMRZ"]["metrics"]["yieldTTM"])
        self.assertEqual(rows["WOSG.L"]["metrics"]["currency"], "GBP")
        self.assertEqual(rows["WOSG.L"]["metrics"]["price"], 7.20)
        self.assertEqual({row["ticker"] for row in rows.values() if row["status"] == "NEW" and row["metrics"]["yieldAbove3"]}, {"REXR", "SFC.TO", "POOL", "ARE", "ALX"})

    def test_latest_report_is_selected_and_ids_cannot_repeat(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder) / "numantia"
            directory.mkdir()
            source = self.report()
            (directory / "first.json").write_text(json.dumps(source))
            (directory / "duplicate.json").write_text(json.dumps(source))
            with self.assertRaisesRegex(ValueError, "Duplicate fund report"):
                load_fund_portfolios(Path(folder))


if __name__ == "__main__":
    unittest.main()
