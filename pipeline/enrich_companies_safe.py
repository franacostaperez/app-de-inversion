#!/usr/bin/env python3
"""Defensive wrapper around enrich_companies for anomalous market data.

Yahoo can occasionally return a zero regularMarketPrice for otherwise valid
securities. The base enricher derives dividend yield from that value and older
versions abort the whole weekly job with ZeroDivisionError. This wrapper keeps
the enrichment best-effort: invalid/non-positive prices are treated as missing
instead of terminating the cadence.
"""

from __future__ import annotations

import math

import enrich_companies as base


OriginalMarketDataClient = base.MarketDataClient


class SafeMarketDataClient(OriginalMarketDataClient):
    """Market-data client that degrades gracefully on invalid Yahoo prices."""

    def yahoo_history_metrics(self, ticker: str) -> dict:
        try:
            return super().yahoo_history_metrics(ticker)
        except ZeroDivisionError:
            # Yahoo occasionally reports regularMarketPrice=0. A zero price is
            # not a usable quote; keep the company and continue without any
            # metrics derived from that value.
            return {
                "_movingAverage1000Unavailable": True,
                "_invalidMarketPrice": True,
            }

    def yahoo_profile(self, ticker: str) -> dict:
        profile = super().yahoo_profile(ticker)
        price = profile.get("marketPrice")
        if price is not None:
            try:
                valid_price = math.isfinite(float(price)) and float(price) > 0
            except (TypeError, ValueError):
                valid_price = False
            if not valid_price:
                profile.pop("marketPrice", None)
                # Do not retain ratios/averages that depend on an invalid quote.
                for key in (
                    "dividendYield",
                    "yahooDividendYield",
                    "movingAverage1000",
                    "priceVsMovingAverage1000Percent",
                    "movingAverage1000Sessions",
                    "movingAverage1000AsOf",
                    "priceHistorySource",
                ):
                    profile.pop(key, None)
                profile["_invalidMarketPrice"] = True
        return profile


def main() -> None:
    base.MarketDataClient = SafeMarketDataClient
    base.main()


if __name__ == "__main__":
    main()
