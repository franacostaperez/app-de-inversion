#!/usr/bin/env python3
"""Build the public, app-ready snapshot from normalized quarterly data."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path


SECTOR_PE_BENCHMARKS = {
    "Technology": 25, "Communication Services": 22, "Consumer Discretionary": 22,
    "Consumer Staples": 22, "Financials": 14, "Energy": 14, "Healthcare": 20,
    "Industrials": 20, "Materials": 16, "Real Estate": 18, "Utilities": 18,
}
BRAND_MULTIPLIERS = {"high": 1.25, "medium": 1.10, "low": 1.0}


def aggregate_holdings(items: list[dict]) -> list[dict]:
    aggregated: dict[str, dict] = {}
    for item in items:
        key = item.get("cusip") or item["ticker"]
        if key not in aggregated:
            aggregated[key] = {**item, "shares": 0, "value": 0}
        aggregated[key]["shares"] += item.get("shares", 0)
        aggregated[key]["value"] += item.get("value", 0)
    return list(aggregated.values())


def estimate_average_purchase_prices(filings: list[dict]) -> dict[tuple[str, str], float]:
    """Estimate cost basis from quarterly 13F snapshots.

    13F does not disclose transaction prices. New shares are valued at the
    reported quarter-end value per share; reductions retain the prior estimate.
    """
    state: dict[tuple[str, str], tuple[float, float]] = {}
    for filing in sorted(filings, key=lambda item: (item.get("reportDate", ""), item.get("filingDate", ""))):
        investor_id = filing.get("investorId")
        if not investor_id:
            continue
        current = {
            item.get("cusip") or item.get("ticker"): item
            for item in aggregate_holdings(filing.get("holdings", []))
        }
        prior_keys = {key[1] for key in state if key[0] == investor_id}
        for security_id in prior_keys - current.keys():
            state.pop((investor_id, security_id), None)
        for security_id, holding in current.items():
            shares = holding.get("shares", 0)
            if not security_id or shares <= 0:
                continue
            reported_price = holding.get("value", 0) / shares
            previous_shares, previous_cost = state.get((investor_id, security_id), (0, reported_price))
            if shares > previous_shares:
                added = shares - previous_shares
                average = ((previous_shares * previous_cost) + (added * reported_price)) / shares
            else:
                average = previous_cost
            state[(investor_id, security_id)] = (shares, round(average, 4))
    return {key: value[1] for key, value in state.items()}


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
    active_investors = {item["id"] for item in current.get("investors", [])}
    updates = {
        item["accessionNumber"]: item
        for item in prior_updates
        if retained_filing_date(item["filingDate"]) and item.get("investorId") in active_investors
    }
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


def build(current: dict, previous: dict, companies: list[dict], company_profiles: list[dict] | None = None, prior_updates: list[dict] | None = None, average_prices: dict[tuple[str, str], float] | None = None, company_reports: list[dict] | None = None) -> dict:
    old_investors = {item["id"]: item for item in previous.get("investors", [])}
    company_by_ticker = {item["ticker"]: item for item in companies}
    company_by_cusip = {item["cusip"]: item for item in companies if item.get("cusip")}
    holding_name_by_ticker = {
        holding["ticker"]: holding.get("company", holding["ticker"])
        for investor in current.get("investors", [])
        for holding in investor.get("holdings", [])
    }
    movements = []
    holdings = []
    consensus = defaultdict(lambda: {"holders": 0, "buying": 0, "selling": 0})
    consensus_names = {}

    for investor in current.get("investors", []):
        old = old_investors.get(investor["id"], {})
        old_items = aggregate_holdings(old.get("holdings", []))
        current_items = aggregate_holdings(investor.get("holdings", []))
        old_holdings = {item.get("cusip", item["ticker"]): item for item in old_items}
        new_holdings = {item.get("cusip", item["ticker"]): item for item in current_items}
        portfolio_value = investor.get("portfolioValue", 0)
        for holding in current_items:
            value = holding.get("value", 0)
            security_id = holding.get("cusip", holding["ticker"])
            holdings.append({
                "investorId": investor["id"],
                "investorName": investor["name"],
                "ticker": holding["ticker"],
                "cusip": holding.get("cusip", holding["ticker"]),
                "company": holding.get("company", holding["ticker"]),
                "shares": holding.get("shares", 0),
                "value": value,
                "weight": round(value / portfolio_value * 100, 4) if portfolio_value else 0,
                "estimatedAveragePurchasePrice": (average_prices or {}).get((investor["id"], security_id)),
            })
        for security_id in sorted(old_holdings.keys() | new_holdings.keys()):
            old_shares = old_holdings.get(security_id, {}).get("shares", 0)
            holding = new_holdings.get(security_id, old_holdings.get(security_id, {}))
            ticker = holding["ticker"]
            new_shares = new_holdings.get(security_id, {}).get("shares", 0)
            action, change = classify(old_shares, new_shares)
            consensus_names[security_id] = holding.get("company", ticker)
            if new_shares > 0:
                consensus[security_id]["holders"] += 1
            if action in ("NEW", "INCREASED"):
                consensus[security_id]["buying"] += 1
            elif action in ("SOLD", "REDUCED"):
                consensus[security_id]["selling"] += 1
            if action != "UNCHANGED":
                movements.append({
                    "investorId": investor["id"],
                    "investorName": investor["name"],
                    "ticker": ticker,
                    "cusip": holding.get("cusip", security_id),
                    "company": holding.get("company", ticker),
                    "action": action,
                    "shares": new_shares,
                    "previousShares": old_shares,
                    "changePercent": change,
                })

    consensus_items = []
    profiles_by_cusip = {item["cusip"]: item for item in (company_profiles or [])}
    for ticker, counts in consensus.items():
        company = company_by_cusip.get(ticker, company_by_ticker.get(ticker, {}))
        profile = profiles_by_cusip.get(ticker, {})
        dividend_yield = profile.get("dividendYield")
        yield_percent = dividend_yield * 100 if dividend_yield is not None else company.get("yield")
        pe = profile.get("peRatio", company.get("pe"))
        sector = profile.get("sector", company.get("sector", "Unknown"))
        brand_strength = profile.get("brandStrength", "low")
        sector_pe = SECTOR_PE_BENCHMARKS.get(sector, 18)
        adjusted_pe_benchmark = round(sector_pe * BRAND_MULTIPLIERS.get(brand_strength, 1.0), 1)
        net_buying = counts["buying"] - counts["selling"]
        if yield_percent is None or yield_percent <= 0:
            dividend_score = 0
        elif yield_percent < 1:
            dividend_score = 8
        elif yield_percent < 2:
            dividend_score = 20
        elif yield_percent < 3:
            dividend_score = 35
        elif yield_percent <= 9:
            dividend_score = 55
        elif yield_percent <= 12:
            dividend_score = 22
        else:
            dividend_score = 8

        if pe is None:
            valuation_score = 7
        elif pe <= 0:
            valuation_score = 0
        elif pe / adjusted_pe_benchmark < 0.5:
            valuation_score = 12
        elif pe / adjusted_pe_benchmark <= 0.85:
            valuation_score = 25
        elif pe / adjusted_pe_benchmark <= 1.10:
            valuation_score = 22
        elif pe / adjusted_pe_benchmark <= 1.30:
            valuation_score = 15
        elif pe / adjusted_pe_benchmark <= 1.60:
            valuation_score = 8
        else:
            valuation_score = 3

        consensus_score = min(12, counts["holders"] * 2) + max(-8, min(8, net_buying * 2))
        consensus_score = max(0, min(20, consensus_score))
        score = dividend_score + valuation_score + consensus_score
        consensus_items.append({
            "ticker": profile.get("ticker", ticker),
            "cusip": ticker,
            "company": profile.get("name", company.get("company", consensus_names.get(ticker, holding_name_by_ticker.get(ticker, ticker)))),
            **counts,
            "yield": yield_percent,
            "pe": pe,
            "opportunityScore": min(100, score),
            "dividendInvestorScore": dividend_score,
            "valuationInvestorScore": valuation_score,
            "consensusInvestorScore": consensus_score,
            "sector": sector,
            "sectorPEBenchmark": adjusted_pe_benchmark,
            "brandPremiumApplied": brand_strength in ("high", "medium"),
        })
    consensus_items.sort(key=lambda item: (item["opportunityScore"], item["buying"], item["holders"]), reverse=True)

    opportunities = []
    for company in (item for item in companies if item.get("metricsStatus") == "verified"):
        signal = consensus[company.get("cusip", company["ticker"])]
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
    investors.sort(key=lambda item: item["portfolioValue"], reverse=True)
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
        "companyReports": sorted(
            [item for item in (company_reports or []) if str(item.get("form", "")).upper().startswith(("10-K", "20-F", "40-F"))],
            key=lambda item: (item["filingDate"], item.get("accessionNumber", ""), item.get("cusip", "")),
            reverse=True,
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--companies", type=Path, required=True)
    parser.add_argument("--company-database", type=Path)
    parser.add_argument("--qualitative-database", type=Path)
    parser.add_argument("--valuation-database", type=Path)
    parser.add_argument("--filings-directory", type=Path)
    parser.add_argument("--company-reports-directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    current = json.loads(args.current.read_text())
    previous = json.loads(args.previous.read_text())
    companies = json.loads(args.companies.read_text())
    profiles = json.loads(args.company_database.read_text()) if args.company_database and args.company_database.exists() else []
    qualitative = json.loads(args.qualitative_database.read_text()) if args.qualitative_database and args.qualitative_database.exists() else []
    valuation = json.loads(args.valuation_database.read_text()) if args.valuation_database and args.valuation_database.exists() else []
    profiles_by_cusip = {item["cusip"]: item for item in profiles}
    for research in qualitative:
        profiles_by_cusip[research["cusip"]] = {**profiles_by_cusip.get(research["cusip"], {}), **research}
    for settings in valuation:
        profiles_by_cusip[settings["cusip"]] = {**profiles_by_cusip.get(settings["cusip"], {}), **settings}
    profiles = sorted(profiles_by_cusip.values(), key=lambda item: item.get("name", ""))
    existing = json.loads(args.output.read_text()) if args.output.exists() else {}
    archived_filings = []
    if args.filings_directory and args.filings_directory.exists():
        archived_filings = [json.loads(path.read_text()) for path in args.filings_directory.glob("*/*.json")]
    company_reports = []
    if args.company_reports_directory and args.company_reports_directory.exists():
        company_reports = [json.loads(path.read_text()) for path in args.company_reports_directory.glob("*/*.json")]
    average_prices = estimate_average_purchase_prices(archived_filings)
    snapshot = build(current, previous, companies, profiles, existing.get("filingUpdates", []), average_prices, company_reports)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
