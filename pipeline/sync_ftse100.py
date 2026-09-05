#!/usr/bin/env python3
"""Synchronize the current FTSE 100 constituents into the company catalogue."""

from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

DEFAULT_URL = "https://en.wikipedia.org/wiki/FTSE_100_Index"
USER_AGENT = "DividendIntelligence/1.0 (franacostaperez@gmail.com)"


class TablesParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_table = False
        self.in_cell = False
        self.cell_parts: list[str] = []
        self.row: list[str] = []
        self.table: list[list[str]] = []
        self.tables: list[list[list[str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self.in_table = True
            self.table = []
        elif self.in_table and tag in ("td", "th"):
            self.in_cell = True
            self.cell_parts = []

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.in_table and tag in ("td", "th") and self.in_cell:
            self.row.append(" ".join("".join(self.cell_parts).split()))
            self.in_cell = False
        elif self.in_table and tag == "tr":
            if self.row:
                self.table.append(self.row)
            self.row = []
        elif self.in_table and tag == "table":
            if self.table:
                self.tables.append(self.table)
            self.in_table = False


def parse_constituents(html: str) -> list[dict]:
    parser = TablesParser()
    parser.feed(html)
    table = next((rows for rows in parser.tables if rows and {"Company", "Ticker"}.issubset(rows[0])), None)
    if not table:
        raise ValueError("No se encontró la tabla de componentes del FTSE 100")
    headers = table[0]
    sector_header = next((value for value in headers if "sector" in value.lower()), None)
    if not sector_header:
        raise ValueError(f"Columnas inesperadas: {headers}")
    result = []
    for values in table[1:]:
        if len(values) < len(headers):
            continue
        row = dict(zip(headers, values))
        london_symbol = row["Ticker"].strip().upper()
        yahoo_symbol = london_symbol.replace(".", "-") + ".L"
        if london_symbol:
            result.append({
                "ticker": yahoo_symbol,
                "londonTicker": london_symbol,
                "name": row["Company"],
                "sector": row[sector_header],
            })
    if not 95 <= len(result) <= 105:
        raise ValueError(f"Se encontraron {len(result)} componentes; se esperaban aproximadamente 100")
    return result


def merge_catalog(catalog: list[dict], constituents: list[dict], now: str) -> tuple[list[dict], int]:
    by_ticker = {str(item.get("ticker", "")).upper(): item for item in catalog if item.get("ticker")}
    added = 0
    for member in constituents:
        item = by_ticker.get(member["ticker"])
        if item is None:
            item = {
                "cusip": f"FTSE100:{member['londonTicker']}",
                "ticker": member["ticker"],
                "name": member["name"],
                "exchange": "LON",
                "currency": "GBX",
                "country": "United Kingdom",
                "paysDividend": None,
                "dividendPerShare": None,
                "dividendYield": None,
                "peRatio": None,
                "source": "FTSE 100 constituents; market data pending",
                "status": "identified",
                "updatedAt": now,
            }
            catalog.append(item)
            by_ticker[member["ticker"]] = item
            added += 1
        item["ftse100"] = True
        item["ftse100Sector"] = member["sector"]
        item["londonTicker"] = member["londonTicker"]
        if not item.get("sector"):
            item["sector"] = member["sector"]
    current = {member["ticker"] for member in constituents}
    for item in catalog:
        if item.get("ftse100") and str(item.get("ticker", "")).upper() not in current:
            item["ftse100"] = False
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
    print(json.dumps({"constituents": len(members), "added": added}))


if __name__ == "__main__":
    main()
