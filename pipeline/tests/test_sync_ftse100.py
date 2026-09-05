import unittest

from pipeline.sync_ftse100 import merge_catalog, parse_constituents


class SyncFTSE100Tests(unittest.TestCase):
    def test_parse_uses_london_qualified_tickers(self):
        rows = "".join(f"<tr><td>Company {i}</td><td>T{i}</td><td>Sector</td></tr>" for i in range(100))
        html = f"<table><tr><th>Company</th><th>Ticker</th><th>FTSE sector</th></tr>{rows}</table>"
        members = parse_constituents(html)
        self.assertEqual(members[0]["ticker"], "T0.L")
        self.assertEqual(len(members), 100)

    def test_merge_does_not_collide_with_us_ticker(self):
        catalog = [{"cusip": "us", "ticker": "BA", "name": "Boeing"}]
        members = [{"ticker": "BA.L", "londonTicker": "BA", "name": "BAE Systems", "sector": "Aerospace"}]
        result, added = merge_catalog(catalog, members, "2026-09-05T00:00:00Z")
        self.assertEqual(added, 1)
        self.assertEqual({item["ticker"] for item in result}, {"BA", "BA.L"})
        self.assertTrue(next(item for item in result if item["ticker"] == "BA.L")["ftse100"])


if __name__ == "__main__":
    unittest.main()
