import unittest
from datetime import date

from pipeline.xtb_dividends import build_payload, normalize_rows


class XTBDividendsTests(unittest.TestCase):
    def test_deduplicates_notice_ids_and_builds_dashboard(self):
        rows = [
            ["Fecha", "Empresa", "Ticker", "Mercado", "Tipo", "Importe", "Moneda base", "Origen", "Enlace al aviso", "ID aviso"],
            ["04/09/2026", "Alpha", "AAA.US", "Estados Unidos", "Acción", 10.0, "EUR", "Gmail · XTB", "https://example/a", "a"],
            ["04/09/2026", "Alpha", "AAA.US", "Estados Unidos", "Acción", 10.0, "EUR", "Gmail · XTB", "https://example/a", "a"],
            ["03/09/2026", "Beta ETF", "BET.DE", "Alemania", "ETF", 5.0, "EUR", "Gmail · XTB", "https://example/b", "b"],
            ["05/09/2025", "Alpha", "AAA.US", "Estados Unidos", "Acción", 2.0, "EUR", "Gmail · XTB", "https://example/c", "c"],
        ]
        receipts = normalize_rows(rows)
        self.assertEqual(len(receipts), 3)
        payload = build_payload(receipts)
        self.assertEqual(payload["asOf"], "2026-09-04")
        self.assertEqual(payload["summary"]["historicalTotalEUR"], 17.0)
        self.assertEqual(payload["summary"]["currentYearEUR"], 15.0)
        self.assertEqual(payload["summary"]["last12MonthsEUR"], 17.0)
        self.assertEqual(payload["ranking"][0]["ticker"], "AAA.US")
        self.assertEqual(payload["futureIncome"]["status"], "needs_current_portfolio")

    def test_rejects_non_eur_cash_rows(self):
        rows = [
            ["Fecha", "Empresa", "Ticker", "Mercado", "Tipo", "Importe", "Moneda base", "ID aviso"],
            ["04/09/2026", "Alpha", "AAA.US", "US", "Acción", 10, "USD", "a"],
        ]
        with self.assertRaises(ValueError):
            normalize_rows(rows)

    def test_rejects_conflicting_duplicate_notice(self):
        rows = [
            ["Fecha", "Empresa", "Ticker", "Mercado", "Tipo", "Importe", "Moneda base", "ID aviso"],
            ["04/09/2026", "Alpha", "AAA.US", "US", "Acción", 10, "EUR", "a"],
            ["04/09/2026", "Alpha", "AAA.US", "US", "Acción", 11, "EUR", "a"],
        ]
        with self.assertRaises(ValueError):
            normalize_rows(rows)


if __name__ == "__main__":
    unittest.main()
