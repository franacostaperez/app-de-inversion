#!/usr/bin/env python3
"""Refresh company dividend and valuation metrics from Google Finance."""

from __future__ import annotations

import argparse
import difflib
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
import urllib.error
import unicodedata
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
    "02079K305": "GOOGL", "191216100": "KO", "615369105": "MCO", "824348106": "SHW",
    "565394103": "CART", "N97284108": "NBIS", "75734B100": "RDDT", "526057104": "LEN",
    "34631F102": "FPS", "G6683N103": "NU", "21037T109": "CEG", "G5279N105": "KLAR",
    "650111107": "NYT", "46625H100": "JPM", "G54950103": "LIN", "64110L106": "NFLX",
    "91332U101": "U", "576323109": "MTZ", "12572Q105": "CME", "580135101": "MCD",
    "632307104": "NTRA", "144285103": "CRS", "042068205": "ARM", "254687106": "DIS",
    "722304102": "PDD", "57636Q104": "MA", "907818108": "UNP", "22266T109": "CPNG",
    "87305R109": "TTMI", "76155X100": "RVMD", "718172109": "PM", "882508104": "TXN",
    "253868103": "DLR", "530909100": "LLYVA", "316841105": "FIG", "45841N107": "IBKR",
    "546347105": "LPX", "G0403H108": "AON", "03769M106": "APO", "04010E109": "AGX",
    "46120E602": "ISRG", "88160R101": "TSLA", "92537N108": "VRT", "833445109": "SNOW",
    "01741R102": "ATI", "G0260P102": "AS", "69331CAL2": "PCG", "142152107": "CAI",
    "55616P104": "M", "Y2573F102": "FLEX",
}


def normalized_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().upper()
    value = re.sub(r"\b(INCORPORATED|INC|CORPORATION|CORP|COMPANY|CO|PLC|LTD|LIMITED|NV|SA|GROUP|HOLDINGS?|COMMON|COM|SHARES?|SHS|ADR|ADS|CLASS|CL|NEW)\b", " ", value)
    return re.sub(r"[^A-Z0-9]+", " ", value).strip()


def number(value):
    if value in (None, "", "—", "-"):
        return None
    try:
        return float(str(value).replace("$", "").replace("%", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def metric(page: str, label: str) -> float | None:
    patterns = (
        # Current Google Finance markup (2026).
        rf'<div[^>]*>{re.escape(label)}</div>.{{0,900}}?<div class="P6K39c">([^<]+)',
        # Legacy markup retained for reproducibility of fixtures and cached pages.
        rf'<div class="SwQK7">{re.escape(label)}</div><div class="dO6ijd">([^<]+)',
    )
    for pattern in patterns:
        match = re.search(pattern, page, re.DOTALL)
        if match:
            return number(html.unescape(match.group(1)))
    return None


def profile_from_google(cusip: str, name: str, ticker: str, exchange: str, page: str) -> dict:
    yield_percent = metric(page, "Dividend yield")
    if yield_percent is None:
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
        self._sec_by_name = None

    def request(self, url: str, payload: bytes | None = None) -> str:
        headers = {"User-Agent": USER_AGENT}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=payload, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")

    def load_sec_tickers(self) -> None:
        if self._sec_tickers is not None:
            return
        headers = {"User-Agent": os.environ.get("SEC_USER_AGENT", "DividendIntelligence franacostaperez@gmail.com")}
        request = urllib.request.Request("https://www.sec.gov/files/company_tickers.json", headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
        self._sec_tickers = {item["ticker"].upper(): item["cik_str"] for item in payload.values()}
        self._sec_by_name = {normalized_name(item["title"]): item["ticker"].upper() for item in payload.values()}

    def ticker_for_cusip(self, cusip: str, name: str = "") -> str | None:
        if cusip in TICKER_OVERRIDES:
            return TICKER_OVERRIDES[cusip]
        try:
            self.load_sec_tickers()
            target = normalized_name(name)
            if target in self._sec_by_name:
                return self._sec_by_name[target]
            match = difflib.get_close_matches(target, self._sec_by_name.keys(), n=1, cutoff=0.94)
            if match:
                return self._sec_by_name[match[0]]
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            pass
        payload = json.dumps([{"idType": "ID_CUSIP", "idValue": cusip}]).encode()
        result = json.loads(self.request("https://api.openfigi.com/v3/mapping", payload))
        rows = result[0].get("data", []) if result else []
        preferred = next((row for row in rows if row.get("exchCode") == "US" and row.get("marketSector") == "Equity"), None)
        return preferred.get("ticker") if preferred else None

    def yahoo_profile(self, ticker: str) -> dict:
        url = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/" + urllib.parse.quote(ticker)
        url += "?modules=assetProfile,summaryDetail,defaultKeyStatistics,financialData,price"
        result_profile = {}
        try:
            payload = json.loads(self.request(url))
            result = payload.get("quoteSummary", {}).get("result") or []
            if result:
                data = result[0]
                asset = data.get("assetProfile", {})
                summary = data.get("summaryDetail", {})
                stats = data.get("defaultKeyStatistics", {})
                financial = data.get("financialData", {})
                price = data.get("price", {})
                raw = lambda item: item.get("raw") if isinstance(item, dict) else item
                result_profile = {
                    "description": asset.get("longBusinessSummary"),
                    "sector": asset.get("sector"), "industry": asset.get("industry"),
                    "country": asset.get("country"), "website": asset.get("website"),
                    "marketCapitalization": raw(price.get("marketCap")),
                    "marketPrice": raw(financial.get("currentPrice")) or raw(price.get("regularMarketPrice")),
                    "peRatio": raw(summary.get("trailingPE")),
                    "dividendYield": raw(summary.get("dividendYield")),
                    "dividendPerShare": raw(summary.get("dividendRate")),
                    "eps": raw(stats.get("trailingEps")),
                }
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            pass
        if result_profile.get("marketPrice") is None:
            result_profile["marketPrice"] = self.yahoo_chart_price(ticker)
        return result_profile

    def yahoo_chart_price(self, ticker: str) -> float | None:
        """Use Yahoo's lightweight chart response when quoteSummary is throttled."""
        path = "/v8/finance/chart/" + urllib.parse.quote(ticker) + "?range=5d&interval=1d"
        for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
            try:
                payload = json.loads(self.request("https://" + host + path))
                result = payload.get("chart", {}).get("result") or []
                price = (result[0].get("meta") or {}).get("regularMarketPrice") if result else None
                if price is not None:
                    return float(price)
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
                continue
        return None

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
        self.load_sec_tickers()
        cik = self._sec_tickers.get(ticker.upper())
        if cik is None:
            return {}
        request = urllib.request.Request(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            submissions = json.load(response)
        recent = submissions.get("filings", {}).get("recent", {})
        result = {}
        investor_url = submissions.get("investorWebsite") or submissions.get("website")
        if investor_url:
            result["investorRelationsURL"] = investor_url
            result["investorRelationsVerified"] = True
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
        # Historical tickers and debt identities are retained for 13F traceability,
        # but must never be enriched as though they were currently quoted shares.
        if existing.get("quoteEligible") is False:
            continue
        ticker = existing.get("ticker")
        if not ticker:
            if new_count >= max_new:
                continue
            try:
                ticker = client.ticker_for_cusip(cusip, holding.get("company", ""))
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                ticker = None
            new_count += 1
        if not ticker:
            continue
        exchange, page = client.google_quote(ticker, existing.get("exchange"))
        if page:
            refreshed = profile_from_google(cusip, holding.get("company", ticker), ticker, exchange, page)
            # A source omitting a field today must not erase a previously verified
            # value; any newly reported non-null metric still takes precedence.
            for key, value in existing.items():
                if refreshed.get(key) is None and value is not None:
                    refreshed[key] = value
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
            yahoo = client.yahoo_profile(ticker) if hasattr(client, "yahoo_profile") else {}
            for key, value in yahoo.items():
                if value is not None and target.get(key) is None:
                    target[key] = value
            if not target.get("investorRelationsURL") and yahoo.get("website"):
                target["investorRelationsURL"] = yahoo["website"]
                target["investorRelationsVerified"] = False
            if yahoo:
                target["source"] = target.get("source", "Google Finance") + " · Yahoo Finance respaldo"
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
