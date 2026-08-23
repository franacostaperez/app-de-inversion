#!/usr/bin/env python3
"""Refresh company dividend and valuation metrics from Google Finance."""

from __future__ import annotations

import argparse
import html
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USER_AGENT = "Mozilla/5.0 DividendIntelligence/1.0"
EXCHANGES = ("NASDAQ", "NYSE", "NYSEARCA")


def number(value):
    if value in (None, "", "—", "-"):
        return None
    try:
        return float(str(value).replace("$", "").replace("%", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def metric(page: str, label: str) -> float | None:
    pattern = rf'<div class="SwQK7">{re.escape(label)}</div><div class="dO6ijd">([^<]+)'
    match = re.search(pattern, page)
    return number(html.unescape(match.group(1))) if match else None


def profile_from_google(cusip: str, name: str, ticker: str, exchange: str, page: str) -> dict:
    yield_percent = metric(page, "Dividend")
    quarterly_dividend = metric(page, "Quarterly dividend")
    return {
        "cusip": cusip, "name": name, "ticker": ticker, "exchange": exchange,
        "currency": "USD", "country": "United States",
        "paysDividend": bool((yield_percent or 0) > 0),
        "dividendPerShare": round(quarterly_dividend * 4, 4) if quarterly_dividend is not None else None,
        "dividendYield": yield_percent / 100 if yield_percent is not None else None,
        "peRatio": metric(page, "P/E ratio"),
        "source": "Google Finance", "status": "enriched",
        "updatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


class MarketDataClient:
    def request(self, url: str, payload: bytes | None = None) -> str:
        headers = {"User-Agent": USER_AGENT}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=payload, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")

    def ticker_for_cusip(self, cusip: str) -> str | None:
        payload = json.dumps([{"idType": "ID_CUSIP", "idValue": cusip}]).encode()
        result = json.loads(self.request("https://api.openfigi.com/v3/mapping", payload))
        rows = result[0].get("data", []) if result else []
        preferred = next((row for row in rows if row.get("exchCode") == "US" and row.get("marketSector") == "Equity"), None)
        return preferred.get("ticker") if preferred else None

    def google_quote(self, ticker: str, preferred_exchange: str | None = None):
        exchanges = ([preferred_exchange] if preferred_exchange else []) + [item for item in EXCHANGES if item != preferred_exchange]
        for exchange in exchanges:
            url = "https://www.google.com/finance/quote/" + urllib.parse.quote(f"{ticker}:{exchange}") + "?hl=en"
            page = self.request(url)
            if "P/E ratio" in page or "Quarterly dividend" in page or "About" in page:
                return exchange, page
        return None, None


def enrich(holdings: list[dict], catalog: list[dict], client: MarketDataClient, max_new: int) -> list[dict]:
    by_cusip = {item["cusip"]: item for item in catalog}
    unique = {item["cusip"]: item for item in holdings}
    new_count = 0
    for cusip, holding in unique.items():
        existing = by_cusip.get(cusip, {})
        ticker = existing.get("ticker")
        if not ticker:
            if new_count >= max_new:
                continue
            ticker = client.ticker_for_cusip(cusip)
            new_count += 1
        if not ticker:
            continue
        exchange, page = client.google_quote(ticker, existing.get("exchange"))
        if page:
            refreshed = profile_from_google(cusip, holding.get("company", ticker), ticker, exchange, page)
            for key in ("description", "businessModel", "revenueModel", "economicMoat", "sector", "industry"):
                if existing.get(key):
                    refreshed[key] = existing[key]
            by_cusip[cusip] = refreshed
        time.sleep(0.2)
    return sorted(by_cusip.values(), key=lambda item: item.get("name", ""))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--holdings", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--max-new", type=int, default=5)
    args = parser.parse_args()
    source = json.loads(args.holdings.read_text())
    holdings = [holding for investor in source.get("investors", []) for holding in investor.get("holdings", [])]
    catalog = json.loads(args.database.read_text()) if args.database.exists() else []
    updated = enrich(holdings, catalog, MarketDataClient(), args.max_new)
    args.database.parent.mkdir(parents=True, exist_ok=True)
    args.database.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
