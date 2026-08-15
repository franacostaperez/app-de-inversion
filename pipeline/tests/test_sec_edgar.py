import unittest

from pipeline.sec_edgar import all_13f_rows, filing_page_url, filing_rows, parse_information_table, quarter_from_date


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
        self.assertEqual([row["accessionNumber"] for row in all_13f_rows({"filings": {"recent": recent}})], ["a", "b"])

    def test_builds_official_filing_page_url(self):
        self.assertEqual(
            filing_page_url("1067983", "0001193125-26-352200"),
            "https://www.sec.gov/Archives/edgar/data/1067983/000119312526352200/0001193125-26-352200-index.html",
        )

    def test_quarter(self):
        self.assertEqual(quarter_from_date("2026-03-31"), "2026-Q1")


if __name__ == "__main__":
    unittest.main()
