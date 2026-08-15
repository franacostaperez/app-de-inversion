#!/usr/bin/env python3
"""Incrementally enrich new 13F issuers and persist profiles in GitHub."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


API_URL = "https://www.alphavantage.co/query"


def number(value: Any) -> float | None:
    if value in (None, "", "None", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def select_symbol(payload: dict, company_name: str) -> str | None:
    matches = payload.get("bestMatches", [])
    eligible = []
    for match in matches:
        score = number(match.get("9. matchScore")) or 0
        region = match.get("4. region", "")
        instrument = match.get("3. type", "")
        if score >= 0.70 and region == "United States" and instrument == "Equity":
            eligible.append((score, match.get("1. symbol")))
    eligible.sort(reverse=True)
    return eligible[0][1] if eligible else None


def profile_from_overview(cusip: str, fallback_name: str, symbol: str, overview: dict) -> dict:
    dividend_per_share = number(overview.get("DividendPerShare"))
    dividend_yield = number(overview.get("DividendYield"))
    return {
        "cusip": cusip,
        "name": overview.get("Name") or fallback_name,
        "ticker": overview.get("Symbol") or symbol,
        "description": overview.get("Description") or None,
        "exchange": overview.get("Exchange") or None,
        "currency": overview.get("Currency") or None,
        "country": overview.get("Country") or None,
        "sector": overview.get("Sector") or None,
        "industry": overview.get("Industry") or None,
        "marketCapitalization": number(overview.get("MarketCapitalization")),
        "paysDividend": bool((dividend_per_share or 0) > 0 or (dividend_yield or 0) > 0),
        "dividendPerShare": dividend_per_share,
        "dividendYield": dividend_yield,
        "peRatio": number(overview.get("PERatio")),
        "eps": number(overview.get("EPS")),
        "source": "Alpha Vantage",
        "status": "enriched",
        "updatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


class AlphaVantageClient:
    def __init__(self, api_key: str, delay_seconds: float = 1.0):
        self.api_key = api_key
        self.delay_seconds = delay_seconds

    def query(self, function: str, **parameters: str) -> dict:
        query = urllib.parse.urlencode({"function": function, "apikey": self.api_key, **parameters})
        with urllib.request.urlopen(f"{API_URL}?{query}", timeout=30) as response:
            payload = json.load(response)
        time.sleep(self.delay_seconds)
        return payload


def enrich(holdings: list[dict], catalog: list[dict], client: AlphaVantageClient, max_new: int) -> list[dict]:
    by_cusip = {item["cusip"]: item for item in catalog}
    unique_holdings = {item["cusip"]: item for item in holdings}
    processed = 0
    for cusip, holding in unique_holdings.items():
        if cusip in by_cusip or processed >= max_new:
            continue
        known_ticker = holding.get("ticker")
        if not known_ticker or known_ticker == cusip:
            search = client.query("SYMBOL_SEARCH", keywords=holding["company"])
            known_ticker = select_symbol(search, holding["company"])
        if not known_ticker:
            by_cusip[cusip] = {
                "cusip": cusip, "name": holding["company"], "status": "pending_symbol",
                "source": "SEC 13F", "updatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
            processed += 1
            continue
        overview = client.query("OVERVIEW", symbol=known_ticker)
        if not overview.get("Symbol"):
            break  # Usually rate limiting: preserve the remaining queue for the next run.
        by_cusip[cusip] = profile_from_overview(cusip, holding["company"], known_ticker, overview)
        processed += 1
    return sorted(by_cusip.values(), key=lambda item: item.get("name", ""))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--holdings", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--max-new", type=int, default=5)
    parser.add_argument("--api-key", default=os.environ.get("ALPHA_VANTAGE_API_KEY"))
    args = parser.parse_args()
    if not args.api_key:
        print("ALPHA_VANTAGE_API_KEY is not configured; skipping company enrichment")
        return
    source = json.loads(args.holdings.read_text())
    holdings = [holding for investor in source.get("investors", []) for holding in investor.get("holdings", [])]
    catalog = json.loads(args.database.read_text()) if args.database.exists() else []
    updated = enrich(holdings, catalog, AlphaVantageClient(args.api_key), args.max_new)
    args.database.parent.mkdir(parents=True, exist_ok=True)
    args.database.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()

