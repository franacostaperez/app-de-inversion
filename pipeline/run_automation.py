#!/usr/bin/env python3
"""Run one data cadence and publish a snapshot only when its inputs change."""

import argparse
import hashlib
import json
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

MODES = ('prices', 'dividends', 'sec', '13f', 'weekly', 'rebuild', 'ftse')
STATE = Path('data/automation/state.json')
SNAPSHOT = Path('data/public/snapshot.json')
INPUTS = ('data/source', 'data/companies', 'data/instruments', 'data/filings',
          'data/company-reports', 'data/fund-portfolios', 'data/config/company_valuation.json',
          'pipeline/build_snapshot.py')
BUILD = ('build_snapshot.py --current data/source/latest.json --previous data/source/previous.json '
         '--companies data/source/companies.json --company-database data/companies/index.json '
         '--qualitative-database data/companies/qualitative.json '
         '--valuation-database data/config/company_valuation.json '
         '--filings-directory data/filings --company-reports-directory data/company-reports '
         '--output data/public/snapshot.json')
FTSE = ('yahoo_company_reports.py --company-database data/companies/index.json '
        '--output data/company-reports/ftse100/yahoo-annual.json '
        '--failures-output data/public/ftse-report-audit.json')
COMMANDS = {
    'prices': ['update_quotes.py'],
    'sec': ['sec_company_reports.py --company-database data/companies/index.json '
            '--qualitative-database data/companies/qualitative.json --output data/company-reports'],
    '13f': [
        'sec_edgar.py --investors data/config/investors.json --companies data/companies/index.json '
        '--current-output data/source/latest.json --previous-output data/source/previous.json '
        '--filings-output data/filings',
        'resolve_instruments.py --holdings data/source/latest.json data/source/previous.json '
        '--company-database data/companies/index.json --mapping-database data/instruments/mappings.json',
    ],
    'weekly': [
        'sync_sp500.py --database data/companies/index.json',
        'sync_ftse100.py --database data/companies/index.json',
        'enrich_companies_safe.py --holdings data/source/latest.json data/source/previous.json '
        '--database data/companies/index.json --manual-companies data/config/portfolio.json --max-new 1000',
        'enrich_qualitative.py --holdings data/source/latest.json '
        '--company-database data/companies/index.json --qualitative-database data/companies/qualitative.json',
        FTSE,
    ],
    'ftse': [FTSE],
    'dividends': [],
    'rebuild': [],
}


def semantic(value):
    """Ignore retrieval timestamps, never filing, valuation or effective dates."""
    if isinstance(value, dict):
        return {k: semantic(v) for k, v in value.items() if k not in ('generatedAt', 'updatedAt')}
    if isinstance(value, list):
        return [semantic(v) for v in value]
    return value


def fingerprint(paths=INPUTS):
    digest = hashlib.sha256()
    for name in paths:
        root = Path(name)
        files = sorted(root.rglob('*.json')) if root.is_dir() else [root]
        for path in files:
            digest.update(str(path).encode())
            if not path.exists():
                digest.update(b'MISSING')
            elif path.suffix == '.json':
                digest.update(json.dumps(semantic(json.loads(path.read_text())), sort_keys=True).encode())
            else:
                digest.update(path.read_bytes())
    return digest.hexdigest()


def run(command):
    print('Running:', command, flush=True)
    args = shlex.split(command)
    subprocess.run([sys.executable, str(Path('pipeline') / args[0]), *args[1:]], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=MODES)
    args = parser.parse_args()
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    for command in COMMANDS[args.mode]:
        run(command)
    current = fingerprint()
    rebuild = args.mode == 'rebuild' or current != state.get('snapshotInputs') or not SNAPSHOT.exists()
    if rebuild:
        # Preserve the existing scoring rules, using only locally cached inputs.
        run(BUILD)
    else:
        print('Snapshot inputs unchanged; skipping snapshot/scoring', flush=True)
    if args.mode == 'dividends':
        run('dividend_events.py --snapshot data/public/snapshot.json '
            '--ir-sources data/config/dividend_ir_sources.json --horizon-days 180 '
            '--max-ir 30 --max-sec 60 --max-alpha 20')
        # Calendar updates used to leave snapshot-core stale until a full rebuild.
        try:
            from .build_snapshot import write_public_snapshot_files
        except ImportError:
            from build_snapshot import write_public_snapshot_files
        write_public_snapshot_files(json.loads(SNAPSHOT.read_text()), SNAPSHOT)
    if args.mode in ('weekly', 'rebuild', 'ftse'):
        run('audit_scoring.py --snapshot data/public/snapshot.json --output data/public/scoring-audit.json')
        run('audit_metric_values.py --snapshot data/public/snapshot.json --output data/public/metric-audit.json')
    state['snapshotInputs'] = current
    state.setdefault('lastSuccess', {})[args.mode] = {
        'at': datetime.now(timezone.utc).isoformat(), 'snapshotRebuilt': rebuild,
    }
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2) + '\n')


if __name__ == '__main__':
    main()
