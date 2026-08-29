import unittest
from datetime import date

from pipeline.dividend_events import extract_event_from_text, estimate_from_alpha_history, parse_ecb_rates


class DividendEventsTests(unittest.TestCase):
    def test_parses_ecb_rates_as_units_per_eur(self):
        document = """<Envelope><Cube><Cube time="2026-08-28">
          <Cube currency="USD" rate="1.1650"/><Cube currency="GBP" rate="0.86120"/>
        </Cube></Cube></Envelope>"""
        result = parse_ecb_rates(document)
        self.assertEqual(result["base"], "EUR")
        self.assertEqual(result["asOf"], "2026-08-28")
        self.assertEqual(result["rates"], {"EUR": 1.0, "USD": 1.165, "GBP": 0.8612})

    def test_extracts_official_ir_event(self):
        text = (
            "Realty Income declared a monthly cash dividend of $0.2710 per share. "
            "The dividend is payable on September 15, 2026 to shareholders of record on August 31, 2026."
        )
        event = extract_event_from_text(
            text,
            ticker="O",
            company="Realty Income Corporation",
            currency="USD",
            source="Investor Relations",
            source_url="https://example.com/dividend",
            source_priority=1,
            confidence=100,
            today=date(2026, 8, 29),
            horizon_days=180,
        )
        self.assertIsNotNone(event)
        self.assertEqual(event["amount"], 0.271)
        self.assertEqual(event["recordDate"], "2026-08-31")
        self.assertEqual(event["paymentDate"], "2026-09-15")
        self.assertEqual(event["status"], "confirmed")
        self.assertEqual(event["source"], "Investor Relations")
        self.assertEqual(event["confidence"], 100)

    def test_estimate_detects_regular_quarterly_raise_period(self):
        rows = []
        payments = [
            ("2024-01-04", 0.415), ("2024-04-04", 0.415), ("2024-07-03", 0.415), ("2024-10-03", 0.4325),
            ("2025-01-09", 0.4325), ("2025-04-03", 0.4325), ("2025-07-03", 0.4325), ("2025-10-09", 0.45),
            ("2026-01-08", 0.45), ("2026-04-02", 0.45), ("2026-07-09", 0.45),
        ]
        for payment, amount in payments:
            rows.append({
                "payment_date": payment,
                "ex_dividend_date": payment,
                "record_date": payment,
                "declaration_date": payment,
                "amount": str(amount),
            })
        payload = {"data": list(reversed(rows))}
        event = estimate_from_alpha_history(
            "VICI", "VICI Properties", "USD", payload,
            today=date(2026, 8, 29), horizon_days=180,
        )
        self.assertIsNotNone(event)
        self.assertEqual(event["status"], "estimated")
        self.assertEqual(event["source"], "Estimación")
        self.assertGreaterEqual(event["confidence"], 60)
        self.assertGreater(event["amount"], 0.45)
        self.assertAlmostEqual(event["amount"], 0.468, delta=0.01)
        self.assertTrue(event["paymentDate"].startswith("2026-10"))
        self.assertIn("subida anual habitual", event["estimatedReason"])


if __name__ == "__main__":
    unittest.main()
