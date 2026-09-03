import unittest

from pipeline.sync_sp500 import merge_catalog, parse_constituents


class SyncSP500Tests(unittest.TestCase):
    def test_parse_rejects_incomplete_source(self):
        with self.assertRaises(ValueError):
            parse_constituents("<html></html>")

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


if __name__ == "__main__":
    unittest.main()
