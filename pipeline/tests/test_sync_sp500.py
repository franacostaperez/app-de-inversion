import unittest

from pipeline.sync_sp500 import merge_catalog, parse_constituents, validate_constituents


class SyncSP500Tests(unittest.TestCase):
    def test_parse_rejects_incomplete_source(self):
        with self.assertRaises(ValueError):
            parse_constituents("<html></html>")

    def test_validation_accepts_503_tickers_for_500_companies(self):
        members = [
            {"ticker": f"T{index}", "cik": str(index + 1).zfill(10)}
            for index in range(500)
        ]
        members.extend([
            {"ticker": "T0.B", "cik": "0000000001"},
            {"ticker": "T1.B", "cik": "0000000002"},
            {"ticker": "T2.B", "cik": "0000000003"},
        ])
        validate_constituents(members)

    def test_validation_rejects_fewer_than_500_companies(self):
        members = [
            {"ticker": f"T{index}", "cik": str(index + 1).zfill(10)}
            for index in range(499)
        ]
        with self.assertRaisesRegex(ValueError, "500 empresas únicas"):
            validate_constituents(members)

    def test_merge_reuses_ticker_and_keeps_share_classes_distinct(self):
        catalog = [{"cusip": "real", "ticker": "GOOG", "name": "Alphabet"}]
        members = [
            {"ticker": "GOOG", "name": "Alphabet C", "sector": "IT", "industry": "Media", "cik": "0001"},
            {"ticker": "GOOGL", "name": "Alphabet A", "sector": "IT", "industry": "Media", "cik": "0001"},
        ]
        result, added = merge_catalog(catalog, members, "2026-09-03T00:00:00Z")
        self.assertEqual(added, 1)
        self.assertEqual({item["ticker"] for item in result}, {"GOOG", "GOOGL"})
        self.assertTrue(all(item["sp500"] for item in result))

    def test_merge_never_attaches_index_membership_to_a_debt_instrument(self):
        catalog = [{
            "cusip": "bond", "ticker": "ABC", "name": "ABC note",
            "quoteEligible": False, "listingStatus": "NON_EQUITY_INSTRUMENT",
            "securityType": "NOTE 1.5%", "sp500": True,
        }]
        members = [{
            "ticker": "ABC", "name": "ABC Inc", "sector": "IT",
            "industry": "Software", "cik": "0000000123",
        }]
        result, added = merge_catalog(catalog, members, "2026-09-04T00:00:00Z")
        selected = [item for item in result if item.get("sp500")]
        self.assertEqual(added, 1)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["cusip"], "SP500:0000000123:ABC")
        self.assertIsNot(selected[0].get("quoteEligible"), False)

    def test_merge_prefers_the_quoted_common_stock_over_a_same_ticker_note(self):
        catalog = [
            {"cusip": "bond", "ticker": "ABC", "quoteEligible": False, "sp500": True},
            {"cusip": "stock", "ticker": "ABC", "quoteEligible": True,
             "listingStatus": "ACTIVE", "securityType": "COM"},
        ]
        members = [{
            "ticker": "ABC", "name": "ABC Inc", "sector": "IT",
            "industry": "Software", "cik": "0000000123",
        }]
        result, added = merge_catalog(catalog, members, "2026-09-04T00:00:00Z")
        selected = [item for item in result if item.get("sp500")]
        self.assertEqual(added, 0)
        self.assertEqual([item["cusip"] for item in selected], ["stock"])


if __name__ == "__main__":
    unittest.main()
