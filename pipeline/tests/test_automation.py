import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import run_automation as automation
from pipeline.update_quotes import refresh


class QuoteClient:
    def yahoo_chart_price(self, ticker):
        return {'A': 120, 'B': None}[ticker]

    def yahoo_fundamental_metrics(self, ticker):
        return {'yahooPeRatio': 15, 'marketCapitalization': 999} if ticker == 'A' else {}


class AutomationTests(unittest.TestCase):
    def test_quotes_preserve_fundamentals_and_failed_tickers(self):
        catalog = [
            {'ticker': 'A', 'marketPrice': 100, 'peRatio': 12, 'dividendYield': .06,
             'movingAverage1000': 80, 'marketCapitalization': 123, 'name': 'A'},
            {'ticker': 'B', 'marketPrice': 5, 'peRatio': 9},
            {'ticker': 'DELISTED', 'quoteEligible': False, 'marketPrice': 3},
        ]
        updated, report = refresh(catalog, QuoteClient)
        self.assertEqual(updated[0]['marketPrice'], 120)
        self.assertEqual(updated[0]['peRatio'], 15)
        self.assertAlmostEqual(updated[0]['dividendYield'], .05)
        self.assertEqual(updated[0]['priceVsMovingAverage1000Percent'], 50)
        self.assertEqual(updated[0]['marketCapitalization'], 123)
        self.assertEqual(updated[1:], catalog[1:])
        self.assertEqual(catalog[0]['marketPrice'], 100)
        self.assertEqual(report['missingPrices'], ['B'])

    def test_total_outage_fails(self):
        with self.assertRaises(RuntimeError):
            refresh([{'ticker': 'B', 'marketPrice': 5}], QuoteClient)

    def test_fingerprint_ignores_refresh_time_but_detects_values_and_new_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'report.json'
            path.write_text(json.dumps({'updatedAt': 'old', 'filingDate': '2026-09-01', 'eps': 2}))
            original = automation.fingerprint([root])
            path.write_text(json.dumps({'updatedAt': 'new', 'filingDate': '2026-09-01', 'eps': 2}))
            self.assertEqual(original, automation.fingerprint([root]))
            path.write_text(json.dumps({'updatedAt': 'new', 'filingDate': '2026-09-02', 'eps': 2}))
            self.assertNotEqual(original, automation.fingerprint([root]))
            previous = automation.fingerprint([root])
            (root / 'new.json').write_text('{}')
            self.assertNotEqual(previous, automation.fingerprint([root]))

    def test_unchanged_sec_skips_snapshot_and_audits(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'state.json'
            snapshot = Path(directory) / 'snapshot.json'
            snapshot.write_text('{}')
            state.write_text(json.dumps({'snapshotInputs': 'same'}))
            with patch.object(automation, 'STATE', state), patch.object(automation, 'SNAPSHOT', snapshot), \
                 patch.object(automation, 'fingerprint', return_value='same'), \
                 patch.object(automation, 'run') as run, patch('sys.argv', ['run_automation.py', 'sec']):
                automation.main()
            self.assertEqual([call.args[0] for call in run.call_args_list], automation.COMMANDS['sec'])

    def test_price_change_rebuilds_without_deep_audit_or_other_collectors(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'state.json'
            snapshot = Path(directory) / 'snapshot.json'
            snapshot.write_text('{}')
            state.write_text(json.dumps({'snapshotInputs': 'old'}))
            with patch.object(automation, 'STATE', state), patch.object(automation, 'SNAPSHOT', snapshot), \
                 patch.object(automation, 'fingerprint', return_value='new'), \
                 patch.object(automation, 'run') as run, patch('sys.argv', ['run_automation.py', 'prices']):
                automation.main()
            self.assertEqual([call.args[0] for call in run.call_args_list], ['update_quotes.py', automation.BUILD])

    def test_calendar_publishes_full_and_core_without_scoring(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'state.json'
            snapshot = Path(directory) / 'snapshot.json'
            snapshot.write_text(json.dumps({'companyReports': [], 'dividendEvents': [{'ticker': 'A'}]}))
            state.write_text(json.dumps({'snapshotInputs': 'same'}))
            with patch.object(automation, 'STATE', state), patch.object(automation, 'SNAPSHOT', snapshot), \
                 patch.object(automation, 'fingerprint', return_value='same'), \
                 patch.object(automation, 'run') as run, patch('sys.argv', ['run_automation.py', 'dividends']):
                automation.main()
            self.assertEqual(run.call_count, 1)
            core = json.loads(snapshot.with_name('snapshot-core.json').read_text())
            self.assertEqual(core['dividendEvents'], [{'ticker': 'A'}])


if __name__ == '__main__':
    unittest.main()
