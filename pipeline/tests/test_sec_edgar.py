import unittest

from pipeline.sec_edgar import filing_rows, parse_information_table, quarter_from_date


XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable><nameOfIssuer>COCA COLA CO</nameOfIssuer><cusip>191216100</cusip><value>25000000</value>
  <shrsOrPrnAmt><sshPrnamt>400000000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
</informationTable>"""


class EdgarTests(unittest.TestCase):
    def test_parses_namespaced_information_table(self):
        result = parse_information_table(XML, {"191216100": "KO"})
        self.assertEqual(result[0]["ticker"], "KO")
        self.assertEqual(result[0]["shares"], 400_000_000)
        self.assertEqual(result[0]["value"], 25_000_000)

    def test_filters_only_original_13f_holdings_reports(self):
        recent = {
            "accessionNumber": ["a", "b", "c"], "filingDate": ["1", "2", "3"],
            "reportDate": ["4", "5", "6"], "form": ["13F-HR", "13F-HR/A", "10-K"],
            "primaryDocument": ["a.xml", "b.xml", "c.htm"],
        }
        self.assertEqual([row["accessionNumber"] for row in filing_rows({"filings": {"recent": recent}})], ["a"])

    def test_quarter(self):
        self.assertEqual(quarter_from_date("2026-03-31"), "2026-Q1")


if __name__ == "__main__":
    unittest.main()

