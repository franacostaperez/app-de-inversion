#!/usr/bin/env python3
"""Refresh company dividend and valuation metrics from Google Finance."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

USER_AGENT = "Mozilla/5.0 DividendIntelligence/1.0"
EXCHANGES = ("NASDAQ", "NYSE", "NYSEARCA")
TICKER_OVERRIDES = {
    "674599105": "OXY", "02079K107": "GOOG", "500754106": "KHC", "009158106": "APD",
    "34959J108": "FTV", "44267T102": "HHH", "72703X106": "PL", "808513105": "SCHW",
    "883556102": "TMO", "571903202": "MAR", "437076102": "HD", "863667101": "SYK",
    "526107107": "LII", "N3167Y103": "RACE", "00217D100": "ASTS", "10806X102": "BBIO",
    "880770102": "TER", "219948106": "CPAY", "097023105": "BA", "59522J103": "MAA",
    "219350105": "GLW", "31428X106": "FDX", "55354G100": "MSCI", "00650F109": "ADPT",
    "171340102": "CHD", "G51502105": "JCI", "742718109": "PG", "88080T104": "WULF",
    "053015103": "ADP", "02005N100": "ALLY",
    "166764100": "CVX", "34959E109": "FTNT", "L8681T102": "SPOT", "45168D104": "IDXX",
    "934423104": "WBD", "133131102": "CPT", "859241101": "STRL", "912008109": "USFD",
    "758750103": "RRX", "829933100": "SIRI", "H5919C104": "ONON", "874054109": "TTWO",
    "09061G101": "BMRN", "670346105": "NUE", "G2004J103": "CCL", "025816109": "AXP",
    "37045V100": "GM", "126650100": "CVS", "530909308": "LLYVK", "314352105": "FDXF",
    "872540109": "TJX", "50212V100": "LPLA", "45866F104": "ICE", "65290E101": "NXT",
    "501044101": "KR", "31946M103": "FCNCA", "00510N102": "TIC", "G3265R107": "APTV",
    "G7997R103": "STX", "58733R102": "MELI", "418056107": "HAS", "747525103": "QCOM",
    "053484101": "AVB", "253393102": "DKS", "29452E101": "EQH", "879433829": "TDS",
    "060505104": "BAC", "37940XAU6": "GPN", "G76279101": "ROIV", "531229755": "FWONK",
    "538034109": "LYV", "49338L103": "KEYS", "88023U101": "SGI", "29444U700": "EQIX",
    "037833100": "AAPL", "285512109": "EA", "922967104": "DERM", "655844108": "NSC",
    "090043AF7": "BILL", "05534B760": "BCE",
}


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
    def __init__(self):
        self._sec_tickers = None

    def request(self, url: str, payload: bytes | None = None) -> str:
        headers = {"User-Agent": USER_AGENT}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=payload, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")

    def ticker_for_cusip(self, cusip: str) -> str | None:
        if cusip in TICKER_OVERRIDES:
            return TICKER_OVERRIDES[cusip]
        payload = json.dumps([{"idType": "ID_CUSIP", "idValue": cusip}]).encode()
        result = json.loads(self.request("https://api.openfigi.com/v3/mapping", payload))
        rows = result[0].get("data", []) if result else []
        preferred = next((row for row in rows if row.get("exchCode") == "US" and row.get("marketSector") == "Equity"), None)
        return preferred.get("ticker") if preferred else None

    def google_quote(self, ticker: str, preferred_exchange: str | None = None):
        exchanges = ([preferred_exchange] if preferred_exchange else []) + [item for item in EXCHANGES if item != preferred_exchange]
        for exchange in exchanges:
            url = "https://www.google.com/finance/quote/" + urllib.parse.quote(f"{ticker}:{exchange}") + "?hl=en"
            try:
                page = self.request(url)
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
                continue
            if "P/E ratio" in page or "Quarterly dividend" in page or "About" in page:
                return exchange, page
        return None, None

    def sec_reports(self, ticker: str) -> dict:
        headers = {"User-Agent": os.environ.get("SEC_USER_AGENT", "DividendIntelligence franacostaperez@gmail.com")}
        if self._sec_tickers is None:
            request = urllib.request.Request("https://www.sec.gov/files/company_tickers.json", headers=headers)
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
            self._sec_tickers = {item["ticker"].upper(): item["cik_str"] for item in payload.values()}
        cik = self._sec_tickers.get(ticker.upper())
        if cik is None:
            return {}
        request = urllib.request.Request(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            recent = json.load(response).get("filings", {}).get("recent", {})
        result = {}
        for desired_form, prefix in (("10-K", "latestAnnualReport"),):
            for index, form in enumerate(recent.get("form", [])):
                if form != desired_form:
                    continue
                accession = recent["accessionNumber"][index]
                document = recent["primaryDocument"][index]
                clean_accession = accession.replace("-", "")
                result[prefix + "URL"] = f"https://www.sec.gov/Archives/edgar/data/{cik}/{clean_accession}/{document}"
                result[prefix + "Date"] = recent["filingDate"][index]
                break
        return result


def enrich(holdings: list[dict], catalog: list[dict], client: MarketDataClient, max_new: int) -> list[dict]:
    by_cusip = {item["cusip"]: item for item in catalog}
    unique = {}
    for item in holdings:
        existing = unique.get(item["cusip"])
        if existing is None or item.get("value", 0) > existing.get("value", 0):
            unique[item["cusip"]] = item
    new_count = 0
    for cusip, holding in sorted(unique.items(), key=lambda pair: pair[1].get("value", 0), reverse=True):
        existing = by_cusip.get(cusip, {})
        ticker = existing.get("ticker")
        if not ticker:
            if new_count >= max_new:
                continue
            try:
                ticker = client.ticker_for_cusip(cusip)
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                ticker = None
            new_count += 1
        if not ticker:
            continue
        exchange, page = client.google_quote(ticker, existing.get("exchange"))
        if page:
            refreshed = profile_from_google(cusip, holding.get("company", ticker), ticker, exchange, page)
            for key in ("description", "businessModel", "revenueModel", "economicMoat", "sector", "industry", "latestQuarterlyReportURL", "latestQuarterlyReportDate", "latestAnnualReportURL", "latestAnnualReportDate"):
                if existing.get(key):
                    refreshed[key] = existing[key]
            by_cusip[cusip] = refreshed
        elif not existing:
            by_cusip[cusip] = {
                "cusip": cusip, "name": holding.get("company", ticker), "ticker": ticker,
                "exchange": None, "currency": "USD", "country": "United States",
                "paysDividend": None, "dividendPerShare": None, "dividendYield": None, "peRatio": None,
                "source": "Google Finance pendiente; informes SEC EDGAR",
                "status": "identified",
                "updatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        target = by_cusip.get(cusip)
        if target and ticker:
            try:
                target.update(client.sec_reports(ticker))
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                pass
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
