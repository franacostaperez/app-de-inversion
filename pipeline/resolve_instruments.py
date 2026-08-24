#!/usr/bin/env python3
"""Resolve 13F identifiers to verified market symbols with persistent evidence."""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


ABBREVIATIONS = {
    "MTR": "MOTOR", "RLTY": "REALTY", "TR": "TRUST", "HLDG": "HOLDINGS",
    "HLDGS": "HOLDINGS", "ENTMT": "ENTERTAINMENT", "INDS": "INDUSTRIES",
    "ELEC": "ELECTRIC", "PWR": "POWER", "PHARMACEUTICALS": "PHARMA",
    "LABORATORIES": "LABS", "INTL": "INTERNATIONAL", "TECH": "TECHNOLOGY",
}
STOP_WORDS = {
    "THE", "INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "PLC",
    "LTD", "LIMITED", "NV", "SA", "SE", "LLC", "LP", "DEL", "NEW", "ORD",
    "COMMON", "COM", "SHARES", "SHS", "STOCK", "CLASS", "CL", "ADR", "ADS",
}
EQUITY_TYPES = {
    "Common Stock", "Depositary Receipt", "REIT", "Equity", "Unit", "ETP",
    # OpenFIGI classifies US-listed ETFs such as SPY, MUB and IWM as Mutual Fund.
    "Mutual Fund",
}

# Instruments which cannot be recovered from a current-symbol directory because
# a corporate action removed the listing, plus one SEC-verified recent listing.
# Keeping these identities explicit prevents a delisted share or a bond from
# receiving a current equity quote merely because its issuer name is similar.
KNOWN_INSTRUMENTS = {
    "29332G102": {
        "ticker": "EHAB", "securityType": "Common Stock", "exchange": "US",
        "listingStatus": "DELISTED_ACQUIRED", "quoteEligible": False,
        "source": "Historical ticker; acquired by Kinderhook", "confidence": 1.0,
        "evidenceURL": "https://investors.ehab.com/news/news-details/2026/Enhabit-Completes-Previously-Announced-Acquisition-by-Kinderhook-Industries-to-Become-a-Private-Company/default.aspx",
    },
    "472145AF8": {
        "ticker": "JAZZ", "securityType": "Convertible Note", "exchange": None,
        "listingStatus": "DEBT_INSTRUMENT", "quoteEligible": False,
        "source": "SEC N-PORT: Jazz note and issuer ticker", "confidence": 1.0,
        "evidenceURL": "https://www.sec.gov/Archives/edgar/data/1710607/000114554925025313/xslFormNPORT-P_X01/primary_doc.xml",
    },
    "554489104": {
        "ticker": "VRE", "securityType": "Common Stock", "exchange": "US",
        "listingStatus": "DELISTED_ACQUIRED", "quoteEligible": False,
        "source": "Historical ticker; acquired by Affinius-led consortium", "confidence": 1.0,
        "evidenceURL": "https://www.sec.gov/Archives/edgar/data/924901/000110465926066981/tm2615596d1_ex99-1.htm",
    },
    "62886HBD2": {
        "ticker": "NCLH", "securityType": "Convertible Note", "exchange": None,
        "listingStatus": "DEBT_INSTRUMENT", "quoteEligible": False,
        "source": "SEC annual report: NCL Corp issuer and listed parent", "confidence": 1.0,
        "evidenceURL": "https://www.sec.gov/Archives/edgar/data/1513761/000110465926022067/nclh-20251231x10k.htm",
    },
    "81211K100": {
        "ticker": "SEE", "securityType": "Common Stock", "exchange": "US",
        "listingStatus": "DELISTED_ACQUIRED", "quoteEligible": False,
        "source": "Historical ticker; acquired by CD&R", "confidence": 1.0,
        "evidenceURL": "https://sealedair.gcs-web.com/news-releases/news-release-details/sealed-air-announces-completion-acquisition-cdr",
    },
    "81619Q105": {
        "ticker": "SEM", "securityType": "Common Stock", "exchange": "US",
        "listingStatus": "DELISTED_ACQUIRED", "quoteEligible": False,
        "source": "Historical ticker; taken private", "confidence": 1.0,
        "evidenceURL": "https://www.sec.gov/Archives/edgar/data/1320414/000110465926079643/tm2619266d7_ex99-1.htm",
    },
    "902685106": {
        "ticker": "UDMY", "successorTicker": "COUR", "securityType": "Common Stock", "exchange": "US",
        "listingStatus": "DELISTED_MERGED", "quoteEligible": False,
        "source": "Historical ticker; merged into Coursera", "confidence": 1.0,
        "evidenceURL": "https://investor.coursera.com/news/news-details/2026/Coursera-Completes-Combination-with-Udemy-to-Build-the-Worlds-Most-Comprehensive-Skills-Platform/default.aspx",
    },
    "G1827P106": {
        "ticker": "CEPT", "successorTicker": "SECZ", "securityType": "Common Stock", "exchange": "US",
        "listingStatus": "DELISTED_BUSINESS_COMBINATION", "quoteEligible": False,
        "source": "Historical ticker; business combination became Securitize", "confidence": 1.0,
        "evidenceURL": "https://www.sec.gov/Archives/edgar/data/2034269/000121390026076435/ea0297280-8k_cantor2.htm",
    },
    "14888U101": {
        "ticker": "CPRX", "securityType": "Common Stock", "exchange": "US",
        "listingStatus": "ACTIVE", "quoteEligible": True,
        "source": "SEC annual report: Nasdaq trading symbol", "confidence": 1.0,
        "evidenceURL": "https://www.sec.gov/Archives/edgar/data/1369568/000119312526071525/cprx-20251231.htm",
    },
    "146280508": {
        "ticker": "SILA", "securityType": "REIT", "exchange": "US",
        "listingStatus": "ACTIVE", "quoteEligible": True,
        "source": "SEC filing: CUSIP and NYSE trading symbol", "confidence": 1.0,
        "evidenceURL": "https://www.sec.gov/Archives/edgar/data/1567925/000156792524000056/ex-99a5cxfaq.htm",
    },
    "16115Q308": {
        "ticker": "GTLS", "securityType": "Common Stock", "exchange": "US",
        "listingStatus": "DELISTED_ACQUIRED", "quoteEligible": False,
        "source": "Historical ticker; acquired by Baker Hughes", "confidence": 1.0,
        "evidenceURL": "https://investors.bakerhughes.com/news/press-releases/news-details/2026/Baker-Hughes-Completes-Acquisition-of-Chart-Industries/default.aspx",
    },
    "29664W105": {
        "ticker": "ESPR", "securityType": "Common Stock", "exchange": "US",
        "listingStatus": "ACTIVE_PENDING_ACQUISITION", "quoteEligible": True,
        "source": "Issuer announcement: Nasdaq trading symbol", "confidence": 1.0,
        "evidenceURL": "https://www.esperion.com/news-releases/news-release-details/esperion-be-acquired-archimed",
    },
    "670703107": {
        "ticker": "NUVL", "securityType": "Common Stock", "exchange": "US",
        "listingStatus": "DELISTED_ACQUIRED", "quoteEligible": False,
        "source": "Historical ticker; acquired by GSK", "confidence": 1.0,
        "evidenceURL": "https://nuvalent.com/",
    },
    "679369108": {
        "ticker": "OLPX", "securityType": "Common Stock", "exchange": "US",
        "listingStatus": "DELISTED_ACQUIRED", "quoteEligible": False,
        "source": "Historical ticker; Nasdaq trading suspended after merger", "confidence": 1.0,
        "evidenceURL": "https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-467",
    },
    "85205TAQ3": {
        "ticker": "SPR", "securityType": "Corporate Bond", "exchange": None,
        "listingStatus": "DEBT_INSTRUMENT_ACQUIRED_ISSUER", "quoteEligible": False,
        "source": "OpenFIGI debt identity; issuer acquired by Boeing", "confidence": 1.0,
        "evidenceURL": "https://investors.boeing.com/investors/news/press-release-details/2025/Boeing-Completes-Acquisition-of-Spirit-AeroSystems/default.aspx",
    },
}


def canonical_name(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().upper()
    tokens = []
    for token in re.findall(r"[A-Z0-9]+", text):
        token = ABBREVIATIONS.get(token, token)
        if token not in STOP_WORDS and not (len(token) == 1 and token.isalpha()):
            tokens.append(token)
    return " ".join(tokens)


def name_confidence(left: str | None, right: str | None) -> float:
    left_name, right_name = canonical_name(left), canonical_name(right)
    if not left_name or not right_name:
        return 0
    if left_name == right_name:
        return 1
    left_tokens, right_tokens = set(left_name.split()), set(right_name.split())
    overlap = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    sequence = difflib.SequenceMatcher(None, left_name, right_name).ratio()
    return round(max(sequence, overlap), 4)


def select_openfigi(rows: list[dict], issuer: str, trusted_identifier: bool = False) -> tuple[dict | None, float]:
    candidates = [
        row for row in rows
        if row.get("ticker") and row.get("marketSector") == "Equity"
        and row.get("securityType2") in EQUITY_TYPES
    ]
    ranked = sorted(
        ((name_confidence(issuer, row.get("name")), row.get("exchCode") == "US", row) for row in candidates),
        key=lambda item: (item[0], item[1]), reverse=True,
    )
    if not ranked or (not trusted_identifier and ranked[0][0] < 0.72):
        return None, ranked[0][0] if ranked else 0
    # A direct CUSIP/FIGI lookup is stronger evidence than issuer-name spelling.
    # Name similarity is still used to choose between multiple share classes.
    return ranked[0][2], max(ranked[0][0], 0.97) if trusted_identifier else ranked[0][0]


class ResolverClient:
    def __init__(self):
        self.openfigi_key = os.environ.get("OPENFIGI_API_KEY")
        try:
            import certifi
            self.ssl_context = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            self.ssl_context = ssl.create_default_context()

    def request_json(self, url: str, data: list[dict] | None = None, headers: dict | None = None) -> tuple[object, dict]:
        request_headers = {"User-Agent": os.environ.get("SEC_USER_AGENT", "DividendIntelligence franacostaperez@gmail.com")}
        request_headers.update(headers or {})
        payload = json.dumps(data).encode() if data is not None else None
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=payload, headers=request_headers)
        with urllib.request.urlopen(request, timeout=45, context=self.ssl_context) as response:
            return json.load(response), dict(response.headers)

    def sec_tickers(self) -> list[dict]:
        payload, _ = self.request_json("https://www.sec.gov/files/company_tickers.json")
        return list(payload.values())

    def openfigi(self, jobs: list[dict]) -> list[dict]:
        headers = {"X-OPENFIGI-APIKEY": self.openfigi_key} if self.openfigi_key else {}
        for attempt in range(5):
            try:
                payload, response_headers = self.request_json("https://api.openfigi.com/v3/mapping", jobs, headers)
                remaining = int(response_headers.get("ratelimit-remaining", "1"))
                if remaining == 0:
                    time.sleep(float(response_headers.get("ratelimit-reset", "3")) + 0.25)
                return payload
            except urllib.error.HTTPError as error:
                if error.code not in (429, 500, 503) or attempt == 4:
                    raise
                time.sleep(min(60, 2 ** attempt * 3))
        return []

    def yahoo_search(self, issuer: str) -> list[dict]:
        query = urllib.parse.quote(issuer)
        for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
            try:
                payload, _ = self.request_json(f"https://{host}/v1/finance/search?q={query}&quotesCount=10&newsCount=0")
                return payload.get("quotes", [])
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                continue
        return []


def resolve(holdings: list[dict], profiles: list[dict], prior: dict, client: ResolverClient) -> tuple[list[dict], dict]:
    unique = {}
    for holding in holdings:
        unique.setdefault(holding["cusip"], holding)
    profiles_by_cusip = {item["cusip"]: item for item in profiles}
    mappings = dict(prior)

    sec_rows = client.sec_tickers()
    sec_by_name = {}
    for row in sec_rows:
        sec_by_name.setdefault(canonical_name(row.get("title")), []).append(row)

    unresolved = []
    issuer_tickers = {}
    for cusip, holding in unique.items():
        existing = profiles_by_cusip.get(cusip, {})
        prior_mapping = mappings.get(cusip) or {}
        ticker = existing.get("ticker") or prior_mapping.get("ticker")
        resolution_source = prior_mapping.get("source") or existing.get("tickerResolutionSource", "")
        if ticker and "Yahoo Finance search" not in resolution_source:
            prior_is_resolved = bool(prior_mapping.get("ticker")) and prior_mapping.get("listingStatus") != "IDENTIFIED_NO_ACTIVE_QUOTE"
            existing_status = existing.get("listingStatus")
            existing_quote_eligible = existing.get("quoteEligible")
            if existing_status == "IDENTIFIED_NO_ACTIVE_QUOTE":
                existing_status, existing_quote_eligible = None, None
            mappings[cusip] = {
                "ticker": ticker,
                "company": holding.get("company"),
                "securityType": prior_mapping.get("securityType") or existing.get("securityType") or holding.get("titleOfClass"),
                "listingStatus": (prior_mapping.get("listingStatus") if prior_is_resolved else None)
                or existing_status or "ACTIVE",
                "quoteEligible": (prior_mapping.get("quoteEligible") if prior_is_resolved else existing_quote_eligible),
                "source": resolution_source if prior_is_resolved else "Existing company profile matched by CUSIP",
                "confidence": prior_mapping.get("confidence", existing.get("tickerResolutionConfidence", 0.95)),
                **({"evidenceURL": prior_mapping["evidenceURL"]} if prior_mapping.get("evidenceURL") else {}),
            }
            if mappings[cusip]["quoteEligible"] is None:
                mappings[cusip]["quoteEligible"] = True
            issuer_tickers.setdefault(canonical_name(holding.get("company")), ticker)
            continue
        if cusip in KNOWN_INSTRUMENTS:
            mappings[cusip] = {"company": holding.get("company"), **KNOWN_INSTRUMENTS[cusip]}
            issuer_tickers.setdefault(canonical_name(holding.get("company")), mappings[cusip]["ticker"])
            continue
        name = canonical_name(holding.get("company"))
        exact = sec_by_name.get(name, [])
        if len(exact) == 1:
            row = exact[0]
            mappings[cusip] = {"ticker": row["ticker"].upper(), "company": holding.get("company"), "source": "SEC company_tickers exact name", "confidence": 1.0}
            issuer_tickers[name] = row["ticker"].upper()
        else:
            matches = difflib.get_close_matches(name, sec_by_name.keys(), n=2, cutoff=0.90)
            if len(matches) == 1 and len(sec_by_name[matches[0]]) == 1:
                row = sec_by_name[matches[0]][0]
                confidence = name_confidence(name, matches[0])
                mappings[cusip] = {"ticker": row["ticker"].upper(), "company": holding.get("company"), "source": "SEC company_tickers fuzzy name", "confidence": confidence}
                issuer_tickers[name] = row["ticker"].upper()
            else:
                unresolved.append((cusip, holding))

    # A ticker verified for another class of the same issuer is valid for identity;
    # OpenFIGI below can still replace it with the exact share-class symbol.
    remaining = []
    for cusip, holding in unresolved:
        inherited = issuer_tickers.get(canonical_name(holding.get("company")))
        if inherited:
            mappings[cusip] = {"ticker": inherited, "company": holding.get("company"), "source": "verified issuer share class", "confidence": 0.92}
        else:
            remaining.append((cusip, holding))

    job_limit = 100 if client.openfigi_key else 5
    for offset in range(0, len(remaining), job_limit):
        batch = remaining[offset:offset + job_limit]
        jobs = []
        for cusip, holding in batch:
            figi = holding.get("figi")
            jobs.append({"idType": "ID_BB_GLOBAL" if figi else ("ID_CINS" if cusip[:1].isalpha() else "ID_CUSIP"), "idValue": figi or cusip})
        try:
            results = client.openfigi(jobs)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            results = [{} for _ in jobs]
        for (cusip, holding), result in zip(batch, results):
            selected, confidence = select_openfigi(
                result.get("data", []), holding.get("company", ""), trusted_identifier=True
            )
            if selected:
                mappings[cusip] = {
                    "ticker": selected["ticker"], "company": holding.get("company"),
                    "figi": selected.get("figi") or holding.get("figi"), "shareClassFIGI": selected.get("shareClassFIGI"),
                    "securityType": selected.get("securityType2"), "exchange": selected.get("exchCode"),
                    "listingStatus": "ACTIVE", "quoteEligible": True,
                    "source": "OpenFIGI " + ("FIGI" if holding.get("figi") else "CUSIP"), "confidence": confidence,
                }

    for cusip, holding in remaining:
        if cusip in mappings:
            continue
        quotes = [row for row in client.yahoo_search(holding.get("company", "")) if row.get("quoteType") == "EQUITY" and row.get("symbol")]
        ranked = sorted(((name_confidence(holding.get("company"), row.get("longname") or row.get("shortname")), row) for row in quotes), reverse=True, key=lambda item: item[0])
        if ranked and ranked[0][0] >= 0.88:
            mappings[cusip] = {"ticker": ranked[0][1]["symbol"], "company": holding.get("company"), "source": "Yahoo Finance search validated by name", "confidence": ranked[0][0]}
        time.sleep(0.15)

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    # Even when an active quote cannot be found, retain the SEC-reported issuer
    # identity so every 13F row is accounted for and can be audited later.
    for cusip, holding in unique.items():
        mappings.setdefault(cusip, {
            "ticker": None,
            "company": holding.get("company"),
            "securityType": holding.get("titleOfClass"),
            "listingStatus": "IDENTIFIED_NO_ACTIVE_QUOTE",
            "quoteEligible": False,
            "source": "SEC Form 13F issuer and CUSIP identity",
            "confidence": 1.0,
        })
    for cusip, mapping in mappings.items():
        if cusip not in unique or not mapping.get("ticker"):
            continue
        mapping.setdefault("securityType", unique[cusip].get("titleOfClass"))
        mapping.setdefault("listingStatus", "ACTIVE")
        mapping.setdefault("quoteEligible", True)
        mapping["updatedAt"] = now
        target = profiles_by_cusip.setdefault(cusip, {"cusip": cusip, "name": unique[cusip].get("company", mapping["ticker"])})
        if not target.get("ticker") or mapping.get("confidence", 0) >= 0.9:
            target["ticker"] = mapping["ticker"]
            target["tickerResolutionSource"] = mapping.get("source")
            target["tickerResolutionConfidence"] = mapping.get("confidence")
            for key in ("securityType", "listingStatus", "quoteEligible", "successorTicker", "evidenceURL"):
                if key in mapping:
                    target[key] = mapping[key]
    return sorted(profiles_by_cusip.values(), key=lambda item: item.get("name", "")), dict(sorted(mappings.items()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--holdings", type=Path, nargs="+", required=True)
    parser.add_argument("--company-database", type=Path, required=True)
    parser.add_argument("--mapping-database", type=Path, required=True)
    args = parser.parse_args()
    sources = [json.loads(path.read_text()) for path in args.holdings]
    holdings = [
        holding
        for source in sources
        for investor in source.get("investors", [])
        for holding in investor.get("holdings", [])
    ]
    profiles = json.loads(args.company_database.read_text()) if args.company_database.exists() else []
    prior = json.loads(args.mapping_database.read_text()) if args.mapping_database.exists() else {}
    profiles, mappings = resolve(holdings, profiles, prior, ResolverClient())
    args.company_database.parent.mkdir(parents=True, exist_ok=True)
    args.mapping_database.parent.mkdir(parents=True, exist_ok=True)
    args.company_database.write_text(json.dumps(profiles, indent=2, ensure_ascii=False) + "\n")
    args.mapping_database.write_text(json.dumps(mappings, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
