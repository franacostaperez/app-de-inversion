#!/usr/bin/env python3
"""Download and normalize the two latest 13F-HR filings from SEC EDGAR."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DATA_BASE = "https://data.sec.gov"
ARCHIVE_BASE = "https://www.sec.gov/Archives/edgar/data"


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
        shares_text = child_text(node, "sshPrnamt") or "0"
        value_text = child_text(node, "value") or "0"
        ticker = ticker_by_cusip.get(cusip, cusip)
        holdings.append({
            "ticker": ticker,
            "cusip": cusip,
            "company": issuer,
            "shares": float(shares_text.replace(",", "")),
            "value": float(value_text.replace(",", "")),
        })
    return holdings


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


def download_information_table(client: SecClient, cik: str, row: dict[str, str], ticker_map: dict[str, str]) -> list[dict[str, Any]]:
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
            return holdings
    raise RuntimeError(f"No information table found for {row['accessionNumber']}")


def quarter_from_date(report_date: str) -> str:
    year, month, _ = (int(part) for part in report_date.split("-"))
    return f"{year}-Q{(month - 1) // 3 + 1}"


def normalize_investor(client: SecClient, investor: dict[str, str], rows: list[dict[str, str]], ticker_map: dict[str, str]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows[:2]:
        holdings = download_information_table(client, investor["cik"], row, ticker_map)
        normalized.append({
            "quarter": quarter_from_date(row["reportDate"]),
            "investor": {
                "id": investor["id"],
                "name": investor["name"],
                "cik": investor["cik"],
                "accessionNumber": row["accessionNumber"],
                "filingDate": f"{row['filingDate']}T00:00:00Z",
                "quarterEnd": f"{row['reportDate']}T00:00:00Z",
                "portfolioValue": sum(item["value"] for item in holdings),
                "holdings": holdings,
            },
        })
    return normalized


def build_quarters(client: SecClient, investors: list[dict[str, str]], ticker_map: dict[str, str]) -> tuple[dict, dict]:
    by_investor: list[dict[str, dict]] = []
    filing_history = []
    for investor in investors:
        cik = investor["cik"].zfill(10)
        submissions = client.json(f"{DATA_BASE}/submissions/CIK{cik}.json")
        for row in all_13f_rows(submissions):
            filing_history.append({
                "investorId": investor["id"],
                "investorName": investor["name"],
                "cik": investor["cik"],
                "form": row["form"],
                "accessionNumber": row["accessionNumber"],
                "filingDate": f"{row['filingDate']}T00:00:00Z",
                "reportDate": f"{row['reportDate']}T00:00:00Z",
                "quarter": quarter_from_date(row["reportDate"]),
                "secURL": filing_page_url(investor["cik"], row["accessionNumber"]),
            })
        normalized = normalize_investor(client, investor, filing_rows(submissions), ticker_map)
        if len(normalized) < 2:
            raise RuntimeError(f"Need two 13F-HR filings for {investor['name']}")
        by_investor.append({item["quarter"]: item["investor"] for item in normalized})
    common_quarters = set.intersection(*(set(items) for items in by_investor))
    ordered = sorted(common_quarters, reverse=True)
    if len(ordered) < 2:
        raise RuntimeError("Need two common reporting quarters")
    return (
        {"quarter": ordered[0], "source": "SEC EDGAR", "investors": [items[ordered[0]] for items in by_investor], "filings": sorted(filing_history, key=lambda item: item["filingDate"], reverse=True)},
        {"quarter": ordered[1], "source": "SEC EDGAR", "investors": [items[ordered[1]] for items in by_investor]},
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
    current, previous = build_quarters(SecClient(args.user_agent), investors, ticker_map)
    for path, payload in ((args.current_output, current), (args.previous_output, previous)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    if args.filings_output:
        archive_filings(current, previous, args.filings_output)


if __name__ == "__main__":
    main()
