import unittest

from pipeline.sync_xtb_eps import streak, quarterly_sec_periods


def period(end, eps):
    return {"periodEnd": end, "eps": eps}


class EPSComparisonsTest(unittest.TestCase):
    def test_yoy_streak_compares_same_quarter_and_stops_on_decline(self):
        rows = [
            period("2026-06-30", 2.2), period("2026-03-31", 1.8),
            period("2025-12-31", 1.6), period("2025-09-30", 1.5),
            period("2025-06-30", 2.0), period("2025-03-31", 1.5),
            period("2024-12-31", 1.7),
        ]
        self.assertEqual(streak(rows, "yoy")["count"], 2)
        self.assertEqual(streak(rows, "qoq")["count"], 3)

    def test_missing_quarter_breaks_continuity(self):
        rows = [
            period("2026-06-30", 3), period("2025-12-31", 2),
            period("2025-06-30", 1),
        ]
        self.assertEqual(streak(rows, "yoy")["count"], 1)
        self.assertEqual(streak(rows, "qoq")["count"], 0)

    def test_sec_excludes_annual_and_ytd_eps(self):
        def item(start, end, value, filed):
            return {
                "start": start, "end": end, "val": value,
                "filed": filed, "form": "10-Q", "accn": "0000000000-26-000001",
            }
        facts = {"facts": {"us-gaap": {"EarningsPerShareDiluted": {
            "units": {"USD/shares": [
                item("2026-01-01", "2026-06-30", 9.0, "2026-08-01"),
                item("2026-04-01", "2026-06-30", 1.5, "2026-08-01"),
                item("2026-04-01", "2026-06-30", 1.6, "2026-09-01"),
            ]}
        }}}}
        from datetime import date
        rows = quarterly_sec_periods(facts, 789019, date(2026, 9, 26))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["eps"], 1.6)


if __name__ == "__main__":
    unittest.main()
