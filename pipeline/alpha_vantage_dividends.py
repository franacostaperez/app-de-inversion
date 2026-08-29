#!/usr/bin/env python3
"""Query Alpha Vantage dividend events without exposing the API key."""

from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request
from datetime import date
from typing import Any

API_URL = "https://www.alphavantage.co/query"


def fetch_dividends(symbol: str, api_key: str) -> dict[str, Any]:
    params = urllib.parse.urlencode({
        "function": "DIVIDENDS",
        "symbol": symbol,
        "apikey": api_key,
    })
    request = urllib.request.Request(
        f"{API_URL}?{params}",
        headers={"User-Agent": "DividendIntelligence/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if "Error Message" in payload:
        raise RuntimeError(payload["Error Message"])
    if "Information" in payload:
        raise RuntimeError(payload["Information"])
    return payload


def normalize_event(symbol: str, event: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "amount": float(event["amount"]) if event.get("amount") not in (None, "") else None,
        "declarationDate": event.get("declaration_date"),
        "exDividendDate": event.get("ex_dividend_date"),
        "recordDate": event.get("record_date"),
        "paymentDate": event.get("payment_date"),
        "status": "confirmed",
        "source": "alpha_vantage",
    }


def future_declared_events(symbol: str, payload: dict[str, Any], today: date | None = None) -> list[dict[str, Any]]:
    today = today or date.today()
    result = []
    for event in payload.get("data", []):
        normalized = normalize_event(symbol, event)
        candidate = normalized.get("paymentDate") or normalized.get("exDividendDate")
        if not candidate:
            continue
        try:
            event_date = date.fromisoformat(candidate)
        except ValueError:
            continue
        if event_date >= today:
            result.append(normalized)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Check declared future dividends in Alpha Vantage")
    parser.add_argument("symbols", nargs="+", help="Ticker symbols to query")
    args = parser.parse_args()

    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        raise SystemExit("ALPHA_VANTAGE_API_KEY is not configured")

    report = {}
    for raw_symbol in args.symbols:
        symbol = raw_symbol.strip().upper()
        payload = fetch_dividends(symbol, api_key)
        report[symbol] = {
            "futureDeclared": future_declared_events(symbol, payload),
            "returnedEvents": len(payload.get("data", [])),
        }

    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
