import unittest

from pipeline.resolve_instruments import canonical_name, is_non_equity_holding, name_confidence, resolve, select_openfigi


class InstrumentResolutionTests(unittest.TestCase):
    def test_verified_common_stock_override_beats_ambiguous_openfigi_class(self):
        class Client:
            openfigi_key = None

            def sec_tickers(self):
                return []

            def openfigi(self, jobs):
                raise AssertionError("The verified override should avoid OpenFIGI")

            def yahoo_search(self, issuer):
                return []

        profiles, mappings = resolve(
            [{"cusip": "053484101", "company": "AVALONBAY CMNTYS INC", "titleOfClass": "COM"}],
            [{"cusip": "053484101", "name": "AVALONBAY CMNTYS INC", "ticker": "AVBC"}],
            {"053484101": {"ticker": "AVBC", "resolutionVersion": 2}}, Client(),
        )
        self.assertEqual(mappings["053484101"]["ticker"], "AVB")
        self.assertEqual(profiles[0]["ticker"], "AVB")

    def test_notes_and_warrants_are_not_quoted_as_common_equity(self):
        self.assertTrue(is_non_equity_holding({"titleOfClass": "NOTE 3.250% 6/1"}))
        self.assertTrue(is_non_equity_holding({"titleOfClass": "*W EXP 11/20/2028"}))
        self.assertFalse(is_non_equity_holding({"titleOfClass": "COM CL A"}))

    def test_normalizes_common_13f_abbreviations(self):
        self.assertEqual(canonical_name("THE AES CORP DEL"), "AES")
        self.assertEqual(canonical_name("ACADIA RLTY TR"), "ACADIA REALTY TRUST")

    def test_selects_equity_instead_of_option(self):
        rows = [
            {"ticker": "ABC 1 C10", "name": "EXAMPLE INC", "marketSector": "Equity", "securityType2": "Option"},
            {"ticker": "ABC", "name": "EXAMPLE INC", "marketSector": "Equity", "securityType2": "Common Stock", "exchCode": "US"},
        ]
        selected, confidence = select_openfigi(rows, "Example Inc")
        self.assertEqual(selected["ticker"], "ABC")
        self.assertEqual(confidence, 1)

    def test_rejects_unrelated_name(self):
        selected, _ = select_openfigi([
            {"ticker": "XYZ", "name": "UNRELATED PLC", "marketSector": "Equity", "securityType2": "Common Stock"}
        ], "Example Inc")
        self.assertIsNone(selected)

    def test_exact_identifier_accepts_openfigi_etf_despite_abbreviated_name(self):
        selected, confidence = select_openfigi([
            {"ticker": "SPY", "name": "SPDR S&P 500 ETF TRUST",
             "marketSector": "Equity", "securityType2": "Mutual Fund", "exchCode": "US"}
        ], "SPDR S&P 500 ETF TR", trusted_identifier=True)
        self.assertEqual(selected["ticker"], "SPY")
        self.assertGreaterEqual(confidence, 0.97)

    def test_name_confidence_accepts_legal_suffix_difference(self):
        self.assertEqual(name_confidence("Adobe Inc", "ADOBE INCORPORATED"), 1)


if __name__ == "__main__":
    unittest.main()
