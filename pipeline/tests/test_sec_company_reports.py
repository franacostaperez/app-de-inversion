import unittest

from pipeline.sec_company_reports import (
    CONCEPTS, build_summary, fact_rows, merge_known, namespace_fact_rows, recent_rows, synthesize_income_statement,
)


class CompanyReportTests(unittest.TestCase):
    def test_qualitative_profile_cannot_erase_verified_ticker(self):
        self.assertEqual(merge_known({"ticker": "AAPL"}, {"ticker": None})["ticker"], "AAPL")

    def test_extracts_every_comparative_period_from_same_filing(self):
        facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
            {"accn": "a", "start": "2024-01-01", "end": "2024-12-31", "val": 90, "fy": 2025, "fp": "FY"},
            {"accn": "a", "start": "2025-01-01", "end": "2025-12-31", "val": 100, "fy": 2025, "fp": "FY"},
            {"accn": "other", "start": "2025-01-01", "end": "2025-12-31", "val": 999},
        ]}}}}}
        concept, periods = fact_rows(facts, "a", ("Revenues",))
        self.assertEqual(concept, "Revenues")
        self.assertEqual([item["value"] for item in periods], [90, 100])

    def test_calculates_margins_and_derived_expenses(self):
        metrics = {
            "revenue": {"periods": [{"value": 100}]},
            "operatingIncome": {"periods": [{"value": 25}]},
            "netIncome": {"periods": [{"value": 15}]},
            "totalDebt": {"periods": [{"value": 40}]},
            "totalAssets": {"periods": [{"value": 200}]},
            "currentLiabilities": {"periods": [{"value": 50}]},
        }
        summary, _ = build_summary(metrics)
        self.assertEqual(summary["expenses"], 75)
        self.assertEqual(summary["operatingMargin"], 25)
        self.assertEqual(summary["netMargin"], 15)
        self.assertEqual(summary["roce"], 16.67)
        self.assertIn("epsDiluted", summary)

    def test_rejects_impossible_operating_margin(self):
        summary, _ = build_summary({
            "revenue": {"periods": [{"value": 7}]},
            "operatingIncome": {"periods": [{"value": 2000}]},
        })
        self.assertIsNone(summary["operatingMargin"])

    def test_prefers_consolidated_revenues_over_ancillary_contract_revenue(self):
        facts = {"facts": {"us-gaap": {
            "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
                {"accn": "a", "start": "2025-01-01", "end": "2025-12-31", "val": 7},
            ]}},
            "Revenues": {"units": {"USD": [
                {"accn": "a", "start": "2025-01-01", "end": "2025-12-31", "val": 3000},
            ]}},
        }}}
        concept, periods = fact_rows(facts, "a", CONCEPTS["revenue"])
        self.assertEqual(concept, "Revenues")
        self.assertEqual(periods[-1]["value"], 3000)

    def test_extracts_ifrs_facts(self):
        facts = {"facts": {"ifrs-full": {"Revenue": {"units": {"EUR": [
            {"accn": "a", "start": "2025-01-01", "end": "2025-12-31", "val": 120},
        ]}}}}}
        concept, periods = namespace_fact_rows(facts, "a", "ifrs-full", ("Revenue",))
        self.assertEqual(concept, "Revenue")
        self.assertEqual(periods[0]["value"], 120)

    def test_extracts_ifrs_dividend_per_share_concept_used_by_tsmc(self):
        facts = {"facts": {"ifrs-full": {"DividendsPaidOrdinarySharesPerShare": {"units": {"TWD/shares": [
            {"accn": "a", "start": "2025-01-01", "end": "2025-12-31", "val": 15},
        ]}}}}}
        concept, periods = namespace_fact_rows(
            facts, "a", "ifrs-full", ("DividendsPaidOrdinarySharesPerShare",)
        )
        self.assertEqual(concept, "DividendsPaidOrdinarySharesPerShare")
        self.assertEqual(periods[0]["value"], 15)

    def test_reconstructs_revenue_and_operating_income_from_standard_subtotals(self):
        period = {"startDate": "2025-01-01", "endDate": "2025-12-31", "unit": "USD"}
        metrics = {
            "grossProfit": {"concept": "GrossProfit", "periods": [{**period, "value": 40}]},
            "costOfRevenue": {"concept": "CostOfRevenue", "periods": [{**period, "value": 60}]},
            "operatingExpenses": {"concept": "OperatingExpenses", "periods": [{**period, "value": 15}]},
        }
        synthesize_income_statement(metrics)
        summary, _ = build_summary(metrics)
        self.assertEqual(summary["revenue"], 100)
        self.assertEqual(summary["operatingIncome"], 25)
        self.assertEqual(summary["operatingMargin"], 25)

    def test_keeps_dividend_per_share_without_calculating_payout(self):
        metrics = {
            "netIncome": {"periods": [{"value": 200}]},
            "dividendsPaid": {"periods": [{"value": 80}]},
            "dividendPerShare": {"periods": [{"value": 2.5}]},
        }
        summary, _ = build_summary(metrics)
        self.assertNotIn("payoutRatio", summary)
        self.assertEqual(summary["dividendPerShare"], 2.5)

    def test_filters_company_reports_to_three_year_window(self):
        submissions = {"filings": {"recent": {
            "accessionNumber": ["new", "old", "quarterly", "ignored"],
            "filingDate": ["2026-01-10", "2020-01-10", "2026-05-10", "2026-01-10"],
            "reportDate": ["2025-12-31", "2019-12-31", "2026-03-31", "2025-12-31"],
            "form": ["10-K", "10-K", "10-Q", "8-K"],
            "primaryDocument": ["new.htm", "old.htm", "quarter.htm", "event.htm"],
        }}}
        self.assertEqual([item["accessionNumber"] for item in recent_rows(submissions)], ["new", "quarterly"])


if __name__ == "__main__":
    unittest.main()
