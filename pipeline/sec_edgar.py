#!/usr/bin/env python3
"""Download and normalize the two latest 13F-HR filings from SEC EDGAR."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
import xml.etree.ElementTree as ET
from statistics import median
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


DATA_BASE = "https://data.sec.gov"
ARCHIVE_BASE = "https://www.sec.gov/Archives/edgar/data"
RETENTION_YEARS = 3
VALUE_NORMALIZATION_VERSION = 1


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child_text(element: ET.Element, name: str) -> str | None:
    for child in element.iter():
        if local_name(child.tag) == name and child.text:
            return child.text.strip()
    return None


def parse_information_table(xml_data: bytes, ticker_by_cusip: dict[str, str]) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_data)
    holdings = []
    for node in root.iter():
        if local_name(node.tag) != "infoTable":
            continue
        cusip = (child_text(node, "cusip") or "").upper().replace(" ", "")
        issuer = child_text(node, "nameOfIssuer") or cusip
        figi = child_text(node, "figi")
        title_of_class = child_text(node, "titleOfClass")
        put_call = child_text(node, "putCall")
        shares_text = child_text(node, "sshPrnamt") or "0"
        value_text = child_text(node, "value") or "0"
        ticker = ticker_by_cusip.get(cusip, cusip)
        holdings.append({
            "ticker": ticker,
            "cusip": cusip,
            "company": issuer,
            "figi": figi,
            "titleOfClass": title_of_class,
            "putCall": put_call,
            "shares": float(shares_text.replace(",", "")),
            "value": float(value_text.replace(",", "")),
        })
    return holdings


def normalize_value_units(holdings: list[dict[str, Any]], market_prices: dict[str, float] | None = None) -> tuple[list[dict[str, Any]], int]:
    """Repair filings that still submit legacy $000 values under the dollar schema.

    Since January 2023 the SEC schema requires nearest-dollar values, but a
    small number of managers continue to submit values in legacy thousands.
    A filing-wide median against quoted equity prices distinguishes the two
    units without changing individual positions selectively.
    """
    market_prices = market_prices or {}
    ratios = []
    for item in holdings:
        title = str(item.get("titleOfClass") or "").upper()
        if item.get("putCall") or any(marker in title for marker in ("NOTE", "BOND", "DEBT", "WARRANT", "W EXP")):
            continue
        shares = item.get("shares") or 0
        price = market_prices.get(item.get("cusip"))
        if shares > 0 and price and price > 0 and item.get("value") is not None:
            ratios.append((item["value"] / shares) / price)
    scale = 1
    if len(ratios) >= 3 and 0.0002 <= median(ratios) <= 0.005:
        scale = 1000
        for item in holdings:
            item["value"] *= scale
            item["valueScaleApplied"] = scale
    return holdings, scale


def filing_rows(submissions: dict[str, Any]) -> list[dict[str, str]]:
    recent = submissions["filings"]["recent"]
    keys = ("accessionNumber", "filingDate", "reportDate", "form", "primaryDocument")
    rows = [dict(zip(keys, values)) for values in zip(*(recent[key] for key in keys))]
    return [row for row in rows if row["form"] == "13F-HR"]


def all_13f_rows(submissions: dict[str, Any]) -> list[dict[str, str]]:
    recent = submissions["filings"]["recent"]
    keys = ("accessionNumber", "filingDate", "reportDate", "form", "primaryDocument")
    rows = [dict(zip(keys, values)) for values in zip(*(recent[key] for key in keys))]
    return [row for row in rows if row["form"].startswith("13F-HR")]


def retention_cutoff(today: date | None = None, years: int = RETENTION_YEARS) -> date:
    today = today or date.today()
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        return today.replace(year=today.year - years, day=28)


def retained_rows(rows: list[dict[str, str]], today: date | None = None) -> list[dict[str, str]]:
    cutoff = retention_cutoff(today)
    return [row for row in rows if date.fromisoformat(row["filingDate"]) >= cutoff]


@dataclass
class SecClient:
    user_agent: str
    delay_seconds: float = 0.12

    def get(self, url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent, "Accept-Encoding": "identity"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read()
        time.sleep(self.delay_seconds)
        return body

    def json(self, url: str) -> dict[str, Any]:
        return json.loads(self.get(url))


def archive_directory(cik: str, accession: str) -> str:
    return f"{ARCHIVE_BASE}/{int(cik)}/{accession.replace('-', '')}"


def filing_page_url(cik: str, accession: str) -> str:
    return f"{archive_directory(cik, accession)}/{accession}-index.html"


def download_information_table(
    client: SecClient, cik: str, row: dict[str, str], ticker_map: dict[str, str],
    market_prices: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    base = archive_directory(cik, row["accessionNumber"])
    index = client.json(f"{base}/index.json")
    candidates = [
        item["name"] for item in index["directory"]["item"]
        if item["name"].lower().endswith(".xml") and item["name"] != row["primaryDocument"]
    ]
    for filename in candidates:
        try:
            holdings = parse_information_table(client.get(f"{base}/{filename}"), ticker_map)
        except ET.ParseError:
            continue
        if holdings:
            return normalize_value_units(holdings, market_prices)[0]
    raise RuntimeError(f"No information table found for {row['accessionNumber']}")


def quarter_from_date(report_date: str) -> str:
    year, month, _ = (int(part) for part in report_date.split("-"))
    return f"{year}-Q{(month - 1) // 3 + 1}"


def normalize_investor(
    client: SecClient, investor: dict[str, str], rows: list[dict[str, str]], ticker_map: dict[str, str],
    market_prices: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    normalized = []
    for row in rows[:2]:
        holdings = download_information_table(client, investor["cik"], row, ticker_map, market_prices)
        normalized.append({
            "quarter": quarter_from_date(row["reportDate"]),
            "investor": {
                "id": investor["id"],
                "name": investor["name"],
                "manager": investor.get("manager"),
                "quarter": quarter_from_date(row["reportDate"]),
                "cik": investor["cik"],
                "accessionNumber": row["accessionNumber"],
                "filingDate": f"{row['filingDate']}T00:00:00Z",
                "quarterEnd": f"{row['reportDate']}T00:00:00Z",
                "portfolioValue": sum(item["value"] for item in holdings),
                "holdings": holdings,
            },
        })
    return normalized


def archive_retained_filings(
    client: SecClient, investor: dict[str, str], rows: list[dict[str, str]], ticker_map: dict[str, str],
    output: Path, market_prices: dict[str, float] | None = None,
) -> set[str]:
    active = set()
    for row in rows:
        accession = row["accessionNumber"]
        active.add(accession)
        destination = output / investor["id"] / f"{accession}.json"
        if destination.exists():
            archived = json.loads(destination.read_text())
            if archived.get("valueNormalizationVersion", 0) >= VALUE_NORMALIZATION_VERSION:
                continue
        holdings = download_information_table(client, investor["cik"], row, ticker_map, market_prices)
        payload = {
            "source": "SEC EDGAR", "investorId": investor["id"], "investorName": investor["name"],
            "manager": investor.get("manager"), "cik": investor["cik"], "accessionNumber": accession,
            "form": row["form"], "filingDate": f"{row['filingDate']}T00:00:00Z",
            "reportDate": f"{row['reportDate']}T00:00:00Z", "quarter": quarter_from_date(row["reportDate"]),
            "portfolioValue": sum(item["value"] for item in holdings),
            "secURL": filing_page_url(investor["cik"], accession),
            "valueNormalizationVersion": VALUE_NORMALIZATION_VERSION, "holdings": holdings,
        }
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return active


def prune_archives(output: Path, active_accessions: set[str]) -> None:
    if not output.exists():
        return
    for path in output.glob("*/*.json"):
        if path.stem not in active_accessions:
            path.unlink()
    for directory in output.iterdir():
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()


def build_quarters(
    client: SecClient, investors: list[dict[str, str]], ticker_map: dict[str, str],
    filings_output: Path | None = None, market_prices: dict[str, float] | None = None,
) -> tuple[dict, dict]:
    current_investors = []
    previous_investors = []
    current_quarters = []
    previous_quarters = []
    filing_history = []
    active_accessions: set[str] = set()
    for investor in investors:
        cik = investor["cik"].zfill(10)
        submissions = client.json(f"{DATA_BASE}/submissions/CIK{cik}.json")
        history_rows = retained_rows(all_13f_rows(submissions))
        original_rows = retained_rows(filing_rows(submissions))
        for row in history_rows:
            filing_history.append({
                "investorId": investor["id"],
                "investorName": investor["name"],
                "manager": investor.get("manager"),
                "cik": investor["cik"],
                "form": row["form"],
                "accessionNumber": row["accessionNumber"],
                "filingDate": f"{row['filingDate']}T00:00:00Z",
                "reportDate": f"{row['reportDate']}T00:00:00Z",
                "quarter": quarter_from_date(row["reportDate"]),
                "secURL": filing_page_url(investor["cik"], row["accessionNumber"]),
            })
        normalized = normalize_investor(client, investor, original_rows, ticker_map, market_prices)
        if len(normalized) < 2:
            raise RuntimeError(f"Need two 13F-HR filings for {investor['name']}")
        current_investors.append(normalized[0]["investor"])
        previous_investors.append(normalized[1]["investor"])
        current_quarters.append(normalized[0]["quarter"])
        previous_quarters.append(normalized[1]["quarter"])
        if filings_output:
            active_accessions |= archive_retained_filings(client, investor, original_rows, ticker_map, filings_output, market_prices)
    if filings_output:
        prune_archives(filings_output, active_accessions)
    return (
        {"quarter": max(current_quarters), "source": "SEC EDGAR", "investors": current_investors, "filings": sorted(filing_history, key=lambda item: item["filingDate"], reverse=True)},
        {"quarter": max(previous_quarters), "source": "SEC EDGAR", "investors": previous_investors},
    )


def archive_filings(current: dict, previous: dict, output: Path) -> None:
    """Persist every downloaded 13F with its complete information table."""
    filings_by_accession = {
        item["accessionNumber"]: item
        for item in current.get("filings", [])
        if item.get("accessionNumber")
    }
    for quarter in (current, previous):
        for investor in quarter.get("investors", []):
            accession = investor.get("accessionNumber")
            if not accession:
                continue
            filing = filings_by_accession.get(accession, {})
            payload = {
                "source": "SEC EDGAR",
                "investorId": investor["id"],
                "investorName": investor["name"],
                "cik": investor.get("cik"),
                "accessionNumber": accession,
                "form": filing.get("form", "13F-HR"),
                "filingDate": investor.get("filingDate"),
                "reportDate": investor.get("quarterEnd"),
                "quarter": quarter["quarter"],
                "portfolioValue": investor.get("portfolioValue", 0),
                "secURL": filing.get("secURL") or filing_page_url(investor["cik"], accession),
                "holdings": investor.get("holdings", []),
            }
            destination = output / investor["id"] / f"{accession}.json"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--investors", type=Path, required=True)
    parser.add_argument("--companies", type=Path, required=True)
    parser.add_argument("--current-output", type=Path, required=True)
    parser.add_argument("--previous-output", type=Path, required=True)
    parser.add_argument("--filings-output", type=Path)
    parser.add_argument("--user-agent", default=os.environ.get("SEC_USER_AGENT"))
    args = parser.parse_args()
    if not args.user_agent or "@" not in args.user_agent:
        parser.error("Set SEC_USER_AGENT to an identifiable value such as 'Dividend Intelligence email@example.com'")
    investors = json.loads(args.investors.read_text())
    companies = json.loads(args.companies.read_text())
    ticker_map = {item["cusip"].upper(): item["ticker"] for item in companies if item.get("cusip")}
    market_prices = {
        item["cusip"].upper(): float(item["marketPrice"])
        for item in companies if item.get("cusip") and item.get("marketPrice")
    }
    current, previous = build_quarters(
        SecClient(args.user_agent), investors, ticker_map, args.filings_output, market_prices
    )
    for path, payload in ((args.current_output, current), (args.previous_output, previous)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
