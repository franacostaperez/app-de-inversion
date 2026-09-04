#!/usr/bin/env python3
"""Synchronize the current S&P 500 constituents into the company catalogue."""

from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

DEFAULT_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
USER_AGENT = "DividendIntelligence/1.0 (franacostaperez@gmail.com)"
EXPECTED_COMPANY_COUNT = 500


class ConstituentsTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_target = False
        self.in_cell = False
        self.cell_parts: list[str] = []
        self.row: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table" and attributes.get("id") == "constituents":
            self.in_target = True
        elif self.in_target and tag in ("td", "th"):
            self.in_cell = True
            self.cell_parts = []

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.in_target and tag in ("td", "th") and self.in_cell:
            self.row.append(" ".join("".join(self.cell_parts).split()))
            self.in_cell = False
        elif self.in_target and tag == "tr":
            if self.row:
                self.rows.append(self.row)
            self.row = []
        elif self.in_target and tag == "table":
            self.in_target = False


def validate_constituents(constituents: list[dict]) -> None:
    unique_ciks = {str(item.get("cik", "")).lstrip("0") for item in constituents}
    unique_ciks.discard("")
    if len(unique_ciks) != EXPECTED_COMPANY_COUNT:
        raise ValueError(
            f"Se esperaban {EXPECTED_COMPANY_COUNT} empresas únicas del S&P 500; "
            f"se encontraron {len(unique_ciks)} en {len(constituents)} valores"
        )


def parse_constituents(html: str) -> list[dict]:
    parser = ConstituentsTableParser()
    parser.feed(html)
    if not parser.rows:
        raise ValueError("No se encontró la tabla constituents del S&P 500")
    headers = parser.rows[0]
    required = {"Symbol", "Security", "GICS Sector", "GICS Sub-Industry", "CIK"}
    if not required.issubset(headers):
        raise ValueError(f"Columnas inesperadas: {headers}")
    result = []
    for values in parser.rows[1:]:
        if len(values) < len(headers):
            continue
        row = dict(zip(headers, values))
        ticker = row["Symbol"].replace(".", "-").upper()
        if ticker:
            result.append({
                "ticker": ticker,
                "name": row["Security"],
                "sector": row["GICS Sector"],
                "industry": row["GICS Sub-Industry"],
                "cik": str(row["CIK"]).zfill(10),
            })
    validate_constituents(result)
    return result


def merge_catalog(catalog: list[dict], constituents: list[dict], now: str) -> tuple[list[dict], int]:
    by_ticker: dict[str, list[dict]] = {}
    for existing in catalog:
        ticker = str(existing.get("ticker", "")).upper()
        if ticker:
            by_ticker.setdefault(ticker, []).append(existing)
        if existing.get("sp500"):
            existing["sp500"] = False

    def quoted_equity(candidates: list[dict]) -> dict | None:
        eligible = [item for item in candidates if item.get("quoteEligible") is not False]
        if not eligible:
            return None
        return max(eligible, key=lambda item: (
            item.get("quoteEligible") is True,
            item.get("listingStatus") == "ACTIVE",
            str(item.get("securityType") or "").upper() in {"COM", "COMMON", "COMMON STOCK"},
            str(item.get("cusip") or "").startswith("SP500:"),
        ))

    added = 0
    for member in constituents:
        candidates = by_ticker.get(member["ticker"], [])
        item = quoted_equity(candidates)
        if item is None:
            synthetic_cusip = f"SP500:{member['cik']}:{member['ticker']}"
            item = next(
                (candidate for candidate in candidates if candidate.get("cusip") == synthetic_cusip),
                None,
            )
        if item is None:
            item = {
                "cusip": f"SP500:{member['cik']}:{member['ticker']}",
                "ticker": member["ticker"],
                "name": member["name"],
                "exchange": None,
                "currency": "USD",
                "country": "United States",
                "paysDividend": None,
                "dividendPerShare": None,
                "dividendYield": None,
                "peRatio": None,
                "source": "S&P 500 constituents; market data pending",
                "status": "identified",
                "updatedAt": now,
            }
            catalog.append(item)
            by_ticker.setdefault(member["ticker"], []).append(item)
            added += 1
        item["sp500"] = True
        item["sp500Sector"] = member["sector"]
        item["sp500Industry"] = member["industry"]
        item["sp500Cik"] = member["cik"]
        if not item.get("sector"):
            item["sector"] = member["sector"]
        if not item.get("industry"):
            item["industry"] = member["industry"]
    return sorted(catalog, key=lambda item: item.get("name", "")), added


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--html", type=Path)
    parser.add_argument("--source-url", default=DEFAULT_URL)
    args = parser.parse_args()
    if args.html:
        html = args.html.read_text(encoding="utf-8")
    else:
        request = urllib.request.Request(args.source_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=45) as response:
            html = response.read().decode("utf-8")
    members = parse_constituents(html)
    catalog = json.loads(args.database.read_text()) if args.database.exists() else []
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    catalog, added = merge_catalog(catalog, members, now)
    args.database.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({
        "companies": len({member["cik"] for member in members}),
        "constituents": len(members),
        "added": added,
    }))


if __name__ == "__main__":
    main()
