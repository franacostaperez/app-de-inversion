#!/usr/bin/env python3
"""Build the public, app-ready snapshot from normalized quarterly data."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path


def aggregate_holdings(items: list[dict]) -> list[dict]:
    aggregated: dict[str, dict] = {}
    for item in items:
        key = item.get("cusip") or item["ticker"]
        if key not in aggregated:
            aggregated[key] = {**item, "shares": 0, "value": 0}
        aggregated[key]["shares"] += item.get("shares", 0)
        aggregated[key]["value"] += item.get("value", 0)
    return list(aggregated.values())


def fallback_filing_history(current: dict, previous: dict) -> list[dict]:
    records = []
    for quarter in (current, previous):
        for investor in quarter.get("investors", []):
            accession = investor.get("accessionNumber")
            cik = investor.get("cik")
            if not accession or not cik:
                continue
            records.append({
                "investorId": investor["id"],
                "investorName": investor["name"],
                "cik": cik,
                "form": "13F-HR",
                "accessionNumber": accession,
                "filingDate": investor["filingDate"],
                "reportDate": investor["quarterEnd"],
                "quarter": quarter["quarter"],
                "secURL": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{accession}-index.html",
            })
    return sorted(records, key=lambda item: item["filingDate"], reverse=True)


def classify(previous: float, current: float) -> tuple[str, float | None]:
    if previous == 0 and current > 0:
        return "NEW", None
    if previous > 0 and current == 0:
        return "SOLD", -100.0
    if current > previous:
        return "INCREASED", round((current / previous - 1) * 100, 2)
    if current < previous:
        return "REDUCED", round((current / previous - 1) * 100, 2)
    return "UNCHANGED", 0.0


def compact_usd(value: float) -> str:
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f} mil M"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f} M"
    return f"${value:,.0f}"


def retained_filing_date(value: str, today: date | None = None) -> bool:
    today = today or date.today()
    try:
        cutoff = today.replace(year=today.year - 3)
    except ValueError:
        cutoff = today.replace(year=today.year - 3, day=28)
    return date.fromisoformat(value[:10]) >= cutoff


def build_filing_updates(current: dict, holdings: list[dict], movements: list[dict], prior_updates: list[dict]) -> list[dict]:
    by_accession = {item["accessionNumber"]: item for item in current.get("filings", [])}
    updates = {item["accessionNumber"]: item for item in prior_updates if retained_filing_date(item["filingDate"])}
    for investor in current.get("investors", []):
        accession = investor.get("accessionNumber")
        filing = by_accession.get(accession)
        if not accession or not filing:
            continue
        investor_holdings = [item for item in holdings if item["investorId"] == investor["id"]]
        investor_movements = [item for item in movements if item["investorId"] == investor["id"]]
        counts = {action: sum(item["action"] == action for item in investor_movements) for action in ("NEW", "INCREASED", "REDUCED", "SOLD")}
        top = max(investor_holdings, key=lambda item: item["value"], default=None)
        top_text = (
            f" La principal posición declarada es {top['company']} ({top['weight']:.1f}% de la cartera)."
            if top else ""
        )
        summary = (
            f"Declaró {len(investor_holdings)} posiciones por un valor aproximado de "
            f"{compact_usd(investor.get('portfolioValue', 0))}. "
            f"Añadió {counts['NEW']}, aumentó {counts['INCREASED']}, redujo {counts['REDUCED']} "
            f"y vendió completamente {counts['SOLD']} posiciones.{top_text}"
        )
        updates[accession] = {
            "investorId": investor["id"],
            "investorName": investor["name"],
            "accessionNumber": accession,
            "filingDate": filing["filingDate"],
            "reportDate": filing["reportDate"],
            "quarter": filing["quarter"],
            "secURL": filing["secURL"],
            "positions": len(investor_holdings),
            "newPositions": counts["NEW"],
            "increasedPositions": counts["INCREASED"],
            "reducedPositions": counts["REDUCED"],
            "soldPositions": counts["SOLD"],
            "portfolioValue": investor.get("portfolioValue", 0),
            "summary": summary,
        }
    return sorted(updates.values(), key=lambda item: item["filingDate"], reverse=True)


def build(current: dict, previous: dict, companies: list[dict], company_profiles: list[dict] | None = None, prior_updates: list[dict] | None = None) -> dict:
    old_investors = {item["id"]: item for item in previous.get("investors", [])}
    company_by_ticker = {item["ticker"]: item for item in companies}
    holding_name_by_ticker = {
        holding["ticker"]: holding.get("company", holding["ticker"])
        for investor in current.get("investors", [])
        for holding in investor.get("holdings", [])
    }
    movements = []
    holdings = []
    consensus = defaultdict(lambda: {"holders": 0, "buying": 0, "selling": 0})

    for investor in current.get("investors", []):
        old = old_investors.get(investor["id"], {})
        old_items = aggregate_holdings(old.get("holdings", []))
        current_items = aggregate_holdings(investor.get("holdings", []))
        old_holdings = {item.get("cusip", item["ticker"]): item for item in old_items}
        new_holdings = {item.get("cusip", item["ticker"]): item for item in current_items}
        portfolio_value = investor.get("portfolioValue", 0)
        for holding in current_items:
            value = holding.get("value", 0)
            holdings.append({
                "investorId": investor["id"],
                "investorName": investor["name"],
                "ticker": holding["ticker"],
                "cusip": holding.get("cusip", holding["ticker"]),
                "company": holding.get("company", holding["ticker"]),
                "shares": holding.get("shares", 0),
                "value": value,
                "weight": round(value / portfolio_value * 100, 4) if portfolio_value else 0,
            })
        for security_id in sorted(old_holdings.keys() | new_holdings.keys()):
            old_shares = old_holdings.get(security_id, {}).get("shares", 0)
            holding = new_holdings.get(security_id, old_holdings.get(security_id, {}))
            ticker = holding["ticker"]
            new_shares = new_holdings.get(security_id, {}).get("shares", 0)
            action, change = classify(old_shares, new_shares)
            if new_shares > 0:
                consensus[ticker]["holders"] += 1
            if action in ("NEW", "INCREASED"):
                consensus[ticker]["buying"] += 1
            elif action in ("SOLD", "REDUCED"):
                consensus[ticker]["selling"] += 1
            if action != "UNCHANGED":
                movements.append({
                    "investorId": investor["id"],
                    "investorName": investor["name"],
                    "ticker": ticker,
                    "company": holding.get("company", ticker),
                    "action": action,
                    "shares": new_shares,
                    "previousShares": old_shares,
                    "changePercent": change,
                })

    consensus_items = []
    for ticker, counts in consensus.items():
        company = company_by_ticker.get(ticker, {})
        consensus_items.append({
            "ticker": ticker,
            "company": company.get("company", holding_name_by_ticker.get(ticker, ticker)),
            **counts,
            "yield": company.get("yield"),
        })
    consensus_items.sort(key=lambda item: (item["buying"], item["holders"]), reverse=True)

    opportunities = []
    for company in (item for item in companies if item.get("metricsStatus") == "verified"):
        signal = consensus[company["ticker"]]
        smart_score = min(100, 50 + signal["buying"] * 12 - signal["selling"] * 10)
        fran_score = round(
            company["valuationScore"] * 0.30
            + company["dividendScore"] * 0.30
            + company["qualityScore"] * 0.20
            + smart_score * 0.20
        )
        opportunities.append({
            **company,
            "smartMoneyScore": smart_score,
            "franScore": fran_score,
            "gurusBuying": signal["buying"],
        })
    opportunities.sort(key=lambda item: item["franScore"], reverse=True)
    holdings.sort(key=lambda item: item["value"], reverse=True)

    investors = [{
        "id": investor["id"], "name": investor["name"], "manager": investor.get("manager"),
        "quarter": investor.get("quarter", current["quarter"]), "filingDate": investor["filingDate"],
        "quarterEnd": investor["quarterEnd"], "portfolioValue": investor["portfolioValue"],
    } for investor in current.get("investors", [])]
    filing_updates = build_filing_updates(current, holdings, movements, prior_updates or [])
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "asOfQuarter": current["quarter"],
        "isDemo": False,
        "opportunities": opportunities,
        "investors": investors,
        "consensus": consensus_items,
        "movements": movements,
        "holdings": holdings,
        "filings": [item for item in (current.get("filings") or fallback_filing_history(current, previous)) if retained_filing_date(item["filingDate"])],
        "filingUpdates": filing_updates,
        "companyProfiles": company_profiles or [],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--companies", type=Path, required=True)
    parser.add_argument("--company-database", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    current = json.loads(args.current.read_text())
    previous = json.loads(args.previous.read_text())
    companies = json.loads(args.companies.read_text())
    profiles = json.loads(args.company_database.read_text()) if args.company_database and args.company_database.exists() else []
    existing = json.loads(args.output.read_text()) if args.output.exists() else {}
    snapshot = build(current, previous, companies, profiles, existing.get("filingUpdates", []))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
