#!/usr/bin/env python3
"""Refresh only quoted prices and trailing P/E, using the existing market client."""

import argparse
import copy
import json
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

try:
    from .enrich_companies import MarketDataClient
except ImportError:
    from enrich_companies import MarketDataClient


def positive(value):
    return isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def refresh(catalog, client_factory=MarketDataClient, workers=4):
    tickers = sorted({row['ticker'] for row in catalog
                      if row.get('ticker') and row.get('quoteEligible') is not False})

    def fetch(ticker):
        client = client_factory()
        price = client.yahoo_chart_price(ticker)
        metrics = client.yahoo_fundamental_metrics(ticker)
        return ticker, price, metrics.get('yahooPeRatio')

    with ThreadPoolExecutor(max_workers=workers) as pool:
        quotes = {ticker: (price, pe) for ticker, price, pe in pool.map(fetch, tickers)}
    report = {
        'attempted': len(tickers),
        'pricesReceived': sum(positive(p) for p, _ in quotes.values()),
        'peReceived': sum(positive(pe) for _, pe in quotes.values()),
        'missingPrices': [t for t, (p, _) in quotes.items() if not positive(p)],
        'missingPE': [t for t, (_, pe) in quotes.items() if not positive(pe)],
    }
    # Do not report a provider outage as a successful refresh or erase cached data.
    if tickers and (report['pricesReceived'] == 0 or report['peReceived'] == 0):
        raise RuntimeError('No usable prices or P/E received: ' + json.dumps(report))
    updated = copy.deepcopy(catalog)
    for row in updated:
        if row.get('quoteEligible') is False or row.get('ticker') not in quotes:
            continue
        price, pe = quotes[row['ticker']]
        if positive(price):
            old_price, old_yield = row.get('marketPrice'), row.get('dividendYield')
            if positive(old_price) and price != old_price and isinstance(old_yield, (int, float)) and old_yield >= 0:
                row['dividendYield'] = old_yield * old_price / price
            row['marketPrice'] = price
            # Derived values must remain consistent with the refreshed price.
            # No dividend or historical-series download is performed here.
            average = row.get('movingAverage1000')
            if positive(average):
                row['priceVsMovingAverage1000Percent'] = round((price / average - 1) * 100, 2)
        if positive(pe):
            row['peRatio'] = pe
            row['yahooPeRatio'] = pe
    return updated, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=Path('data/companies/index.json'))
    parser.add_argument('--report', type=Path, default=Path('data/automation/quotes.json'))
    args = parser.parse_args()
    catalog = json.loads(args.database.read_text())
    updated, report = refresh(catalog)
    if updated != catalog:
        args.database.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + '\n')
    report['checkedAt'] = datetime.now(timezone.utc).isoformat()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
