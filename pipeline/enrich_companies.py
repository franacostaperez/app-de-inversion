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
LIVE_YAHOO_FIELDS = {
    "marketPrice", "marketCapitalization", "movingAverage1000", "priceVsMovingAverage1000Percent",
    "movingAverage1000Sessions", "movingAverage1000AsOf", "priceHistorySource",
}
YAHOO_EXCHANGES = {
    "NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ",
    "NYQ": "NYSE", "ASE": "NYSEAMERICAN", "PCX": "NYSEARCA",
}
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
    "29364G103": "ETR",
}


def normalized_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().upper()
    value = re.sub(r"\b(INCORPORATED|INC|CORPORATION|CORP|COMPANY|CO|PLC|LTD|LIMITED|NV|SA|GROUP|HOLDINGS?|COMMON|COM|SHARES?|SHS|ADR|ADS|CLASS|CL|NEW)\b", " ", value)
    return re.sub(r"[^A-Z0-9]+", " ", value).strip()


def number(value):
    if value in (None, "", "—", "-"):
        return None
    try:
        text = str(value).replace("\xa0", " ").replace("$", "").replace("€", "").replace("%", "").strip()
        text = re.sub(r"[^0-9,.-]", "", text)
        if "," in text and "." not in text:
            text = text.replace(",", ".")
        elif "," in text and "." in text:
            # Google localizes both decimal and thousands separators.
            text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
        return float(text)
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


def google_description(page: str) -> str | None:
    """Extract Google's localized public company overview from the About card."""
    match = re.search(r'class="RaUwRb".{0,1000}?<span[^>]*>(.*?)</span>', page, re.DOTALL)
    if not match:
        return None
    value = html.unescape(re.sub(r"<[^>]+>", " ", match.group(1)))
    value = re.sub(r"\s+", " ", value).strip()
    return value if len(value) >= 40 else None


def profile_from_google(cusip: str, name: str, ticker: str, exchange: str, page: str) -> dict:
    yield_percent = metric(page, "Dividend yield")
    if yield_percent is None:
        yield_percent = metric(page, "Dividend")
    if yield_percent is None:
        yield_percent = metric(page, "Dividendo")
    quarterly_dividend = metric(page, "Quarterly dividend")
    if quarterly_dividend is None:
        quarterly_dividend = metric(page, "Dividendo trimestral")
    pe_ratio = metric(page, "P/E ratio")
    if pe_ratio is None:
        pe_ratio = metric(page, "Ratio PER")
    return {
        "cusip": cusip, "name": name, "ticker": ticker, "exchange": exchange,
        "currency": "USD", "country": "United States",
        "paysDividend": bool((yield_percent or 0) > 0),
        "dividendPerShare": round(quarterly_dividend * 4, 4) if quarterly_dividend is not None else None,
        "dividendYield": yield_percent / 100 if yield_percent is not None else None,
        "googleDividendYield": yield_percent / 100 if yield_percent is not None else None,
        "peRatio": pe_ratio, "googlePeRatio": pe_ratio,
        "description": google_description(page),
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
        # quoteSummary now requires a browser crumb and returns HTTP 401 in
        # unattended jobs. The public time-series and chart endpoints expose
        # the same objective metrics without cookies.
        result_profile = self.yahoo_fundamental_metrics(ticker)
        # Keep valuation history in GitHub as a compact derived metric instead
        # of shipping thousands of daily quotes to every phone.
        history = self.yahoo_history_metrics(ticker)
        for key, value in history.items():
            if value is not None:
                result_profile[key] = value
        if result_profile.get("marketPrice") is None:
            result_profile["marketPrice"] = self.yahoo_chart_price(ticker)
        return result_profile

    def yahoo_fundamental_metrics(self, ticker: str) -> dict:
        """Return latest market cap and trailing P/E from Yahoo time series."""
        encoded = urllib.parse.quote(ticker)
        period2 = int(time.time()) + 86400
        period1 = period2 - 400 * 86400
        path = (
            f"/ws/fundamentals-timeseries/v1/finance/timeseries/{encoded}"
            f"?symbol={encoded}&type=trailingMarketCap,trailingPeRatio"
            f"&period1={period1}&period2={period2}"
        )
        metric_map = {
            "trailingMarketCap": ("marketCapitalization",),
            "trailingPeRatio": ("peRatio", "yahooPeRatio"),
        }
        for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
            try:
                payload = json.loads(self.request("https://" + host + path))
                result = payload.get("timeseries", {}).get("result") or []
                metrics = {}
                for series in result:
                    for source_key, target_keys in metric_map.items():
                        values = series.get(source_key) or []
                        raw = (values[-1].get("reportedValue") or {}).get("raw") if values else None
                        if raw is not None:
                            for target_key in target_keys:
                                metrics[target_key] = float(raw)
                if metrics:
                    return metrics
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, IndexError):
                continue
        return {}

    def yahoo_history_metrics(self, ticker: str) -> dict:
        """Return the 1,000-session adjusted-close average and current discount/premium."""
        path = (
            "/v8/finance/chart/" + urllib.parse.quote(ticker)
            + "?range=5y&interval=1d&events=div&includeAdjustedClose=true"
        )
        for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
            try:
                payload = json.loads(self.request("https://" + host + path))
                results = payload.get("chart", {}).get("result") or []
                if not results:
                    continue
                result = results[0]
                indicators = result.get("indicators") or {}
                adjusted_rows = indicators.get("adjclose") or []
                quote_rows = indicators.get("quote") or []
                values = adjusted_rows[0].get("adjclose", []) if adjusted_rows else []
                if not values and quote_rows:
                    values = quote_rows[0].get("close", [])
                closes = [float(value) for value in values if value is not None and float(value) > 0]
                meta = result.get("meta") or {}
                current = meta.get("regularMarketPrice")
                if current is None and closes:
                    current = closes[-1]
                metrics = {"marketPrice": float(current)} if current is not None else {}
                if meta.get("currency"):
                    metrics["currency"] = meta["currency"]
                exchange = YAHOO_EXCHANGES.get(meta.get("exchangeName"), meta.get("fullExchangeName"))
                if exchange:
                    metrics["exchange"] = exchange
                latest_timestamp = meta.get("regularMarketTime") or (result.get("timestamp") or [None])[-1]
                if current is not None and latest_timestamp:
                    cutoff_timestamp = latest_timestamp - 365.25 * 86400
                    dividends = (result.get("events") or {}).get("dividends") or {}
                    trailing_dividend = sum(
                        float(item.get("amount") or 0)
                        for item in dividends.values()
                        if item.get("date") and item["date"] >= cutoff_timestamp
                    )
                    metrics.update({
                        "dividendPerShare": round(trailing_dividend, 6),
                        "dividendYield": trailing_dividend / float(current),
                        "yahooDividendYield": trailing_dividend / float(current),
                    })
                if len(closes) < 1000:
                    metrics["_movingAverage1000Unavailable"] = True
                    return metrics
                average = sum(closes[-1000:]) / 1000
                timestamps = result.get("timestamp") or []
                as_of = datetime.fromtimestamp(timestamps[-1], timezone.utc).date().isoformat() if timestamps else None
                metrics.update({
                    "movingAverage1000": round(average, 4),
                    "priceVsMovingAverage1000Percent": round((float(current) / average - 1) * 100, 2),
                    "movingAverage1000Sessions": 1000,
                    "movingAverage1000AsOf": as_of,
                    "priceHistorySource": "Yahoo Finance adjusted daily close",
                })
                return metrics
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, IndexError):
                continue
        return {}

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
            # Spanish localization provides a readable About description for
            # the app; metric extraction supports both English and Spanish.
            url = "https://www.google.com/finance/quote/" + urllib.parse.quote(f"{ticker}:{exchange}") + "?hl=es"
            try:
                page = self.request(url)
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
                continue
            if any(marker in page for marker in ("P/E ratio", "Quarterly dividend", "About", "Ratio PER", "Dividendo trimestral", 'class="RaUwRb"')):
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
        if submissions.get("sicDescription"):
            result["industry"] = submissions["sicDescription"]
        if submissions.get("stateOfIncorporationDescription"):
            result["incorporation"] = submissions["stateOfIncorporationDescription"]
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


def normalized_yield(value) -> float | None:
    value = number(value)
    if value is None or value < 0:
        return None
    # Yahoo normally returns a fraction while display pages use percent. Keep
    # the ingestion resilient to either representation.
    if 0.20 < value <= 20:
        value /= 100
    return value if value <= 0.20 else None


def validate_market_metrics(profile: dict) -> dict:
    """Cross-check provider units and quarantine conflicting market metrics."""
    warnings = [item for item in profile.get("metricWarnings", []) if not item.startswith("MARKET_")]
    google_yield = normalized_yield(profile.get("googleDividendYield"))
    yahoo_yield = normalized_yield(profile.get("yahooDividendYield"))
    candidates = [value for value in (google_yield, yahoo_yield) if value is not None]
    if len(candidates) == 2 and abs(candidates[0] - candidates[1]) > max(0.005, max(candidates) * 0.25):
        profile["dividendYield"] = None
        warnings.append("MARKET_YIELD_PROVIDER_CONFLICT")
    elif candidates:
        profile["dividendYield"] = google_yield if google_yield is not None else yahoo_yield
    else:
        profile["dividendYield"] = normalized_yield(profile.get("dividendYield"))

    google_pe, yahoo_pe = number(profile.get("googlePeRatio")), number(profile.get("yahooPeRatio"))
    pe_candidates = [value for value in (google_pe, yahoo_pe) if value is not None and value > 0]
    if len(pe_candidates) == 2 and abs(pe_candidates[0] - pe_candidates[1]) / max(pe_candidates) > 0.35:
        profile["peRatio"] = None
        warnings.append("MARKET_PE_PROVIDER_CONFLICT")
    elif pe_candidates:
        profile["peRatio"] = google_pe if google_pe and google_pe > 0 else yahoo_pe

    price, dividend = number(profile.get("marketPrice")), number(profile.get("dividendPerShare"))
    if price and dividend is not None and profile.get("dividendYield") is not None:
        calculated = dividend / price
        if abs(calculated - profile["dividendYield"]) > max(0.006, profile["dividendYield"] * 0.30):
            warnings.append("MARKET_YIELD_DIFFERS_FROM_DIVIDEND_OVER_PRICE")
    profile["paysDividend"] = (profile.get("dividendYield") or 0) > 0 or (dividend or 0) > 0
    if warnings:
        profile["metricWarnings"] = sorted(set(warnings))
    else:
        profile.pop("metricWarnings", None)
    return profile


def portfolio_holdings(positions: list[dict], catalog: list[dict]) -> list[dict]:
    """Convert manually saved portfolio positions into enrichment candidates."""
    catalog_by_ticker = {
        str(item.get("ticker", "")).upper(): item["cusip"]
        for item in catalog
        if item.get("ticker") and item.get("cusip")
    }
    unique = {}
    for position in positions:
        ticker = str(position.get("ticker", "")).strip().upper()
        if not ticker:
            continue
        unique[ticker] = {
            "cusip": catalog_by_ticker.get(ticker, f"PORTFOLIO:{ticker}"),
            "ticker": ticker,
            "company": position.get("name") or ticker,
            "exchange": position.get("exchange"),
            "value": -1,
        }
    return list(unique.values())


def enrich(holdings: list[dict], catalog: list[dict], client: MarketDataClient, max_new: int) -> list[dict]:
    by_cusip = {item["cusip"]: item for item in catalog}
    unique = {}
    for item in holdings:
        existing = unique.get(item["cusip"])
        if existing is None or item.get("value", 0) > existing.get("value", 0):
            unique[item["cusip"]] = item
    # Refresh the full GitHub catalogue, not only securities present in the
    # latest two 13F quarters. Otherwise an older company can keep a generic
    # profile forever even though its ticker is already known.
    for company in catalog:
        unique.setdefault(company["cusip"], {
            "cusip": company["cusip"],
            "ticker": company.get("ticker"),
            "company": company.get("name") or company.get("ticker") or "Empresa",
            "value": -1,
        })
    new_count = 0
    def enrichment_priority(pair):
        cusip, holding = pair
        return (bool(by_cusip.get(cusip, {}).get("sp500")), holding.get("value", 0))

    for cusip, holding in sorted(unique.items(), key=enrichment_priority, reverse=True):
        existing = by_cusip.get(cusip, {})
        # Historical tickers and debt identities are retained for 13F traceability,
        # but must never be enriched as though they were currently quoted shares.
        if existing.get("quoteEligible") is False:
            continue
        ticker = existing.get("ticker") or holding.get("ticker")
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
        preferred_exchange = existing.get("exchange") or holding.get("exchange")
        exchange, page = client.google_quote(ticker, preferred_exchange)
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
            if yahoo.pop("_movingAverage1000Unavailable", False):
                for key in LIVE_YAHOO_FIELDS - {"marketPrice"}:
                    target.pop(key, None)
            for key, value in yahoo.items():
                if value is not None and (key.startswith("yahoo") or key in LIVE_YAHOO_FIELDS or target.get(key) is None):
                    target[key] = value
            if not target.get("investorRelationsURL") and yahoo.get("website"):
                target["investorRelationsURL"] = yahoo["website"]
                target["investorRelationsVerified"] = False
            if yahoo:
                target["source"] = target.get("source", "Google Finance") + " · Yahoo Finance respaldo"
            validate_market_metrics(target)
            try:
                target.update(client.sec_reports(ticker))
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                pass
        time.sleep(0.2)
    return sorted(by_cusip.values(), key=lambda item: item.get("name", ""))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--holdings", type=Path, nargs="+", required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--manual-companies", type=Path)
    parser.add_argument("--max-new", type=int, default=5)
    args = parser.parse_args()
    sources = [json.loads(path.read_text()) for path in args.holdings]
    holdings = [
        holding
        for source in sources
        for investor in source.get("investors", [])
        for holding in investor.get("holdings", [])
    ]
    catalog = json.loads(args.database.read_text()) if args.database.exists() else []
    if args.manual_companies and args.manual_companies.exists():
        manual = json.loads(args.manual_companies.read_text())
        positions = manual.get("positions", []) if isinstance(manual, dict) else manual
        holdings.extend(portfolio_holdings(positions, catalog))
    updated = enrich(holdings, catalog, MarketDataClient(), args.max_new)
    args.database.parent.mkdir(parents=True, exist_ok=True)
    args.database.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
