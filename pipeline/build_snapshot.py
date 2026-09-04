#!/usr/bin/env python3
"""Build the public, app-ready snapshot from normalized quarterly data."""

from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path


SECTOR_PE_MULTIPLIERS = {
    "Technology": 1.35, "Communication Services": 1.25, "Consumer Discretionary": 1.15,
    "Consumer Staples": 1.15, "Financials": 0.90, "Energy": 0.85, "Healthcare": 1.20,
    "Industrials": 1.10, "Materials": 0.95, "Real Estate": 1.15, "Utilities": 1.05,
}
DIVIDEND_GROWTH_SCORE_MAXIMUM = 5
QUALITY_SCORE_MAXIMUM = 12
OPPORTUNITY_SCORE_MAXIMUM = 97  # 22 + 5 + 35 + 6 + 12 + 7 + 10; no redistribution
BRAND_MULTIPLIERS = {"high": 1.20, "medium": 1.10, "low": 1.0}
QUALITATIVE_PROFILE_FIELDS = {
    "description", "businessModel", "revenueModel", "economicMoat", "brandStrength",
    "investorRelationsURL", "investorRelationsVerified",
}
MARKET_PROFILE_FIELDS = {
    "marketPrice", "marketCapitalization", "dividendYield", "dividendPerShare", "peRatio", "eps",
    "movingAverage1000", "priceVsMovingAverage1000Percent", "movingAverage1000Sessions",
    "movingAverage1000AsOf", "priceHistorySource",
}


def issuer_key(name: str | None) -> str:
    """Return a stable issuer key shared by security classes and ADR variants."""
    text = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\b(class|cl|common|stock|shares?|adr|ads|depositary|units?)\s*[a-z0-9]*\b", " ", text)
    text = re.sub(r"\b(incorporated|inc|corporation|corp|company|co|limited|ltd|plc|sa|nv|llc|lp)\b", " ", text)
    return re.sub(r"[^a-z0-9]+", "", text)


def merge_known(base: dict, preferred: dict) -> dict:
    """Merge records without allowing a missing value to erase known data."""
    result = dict(base)
    result.update({key: value for key, value in preferred.items() if value is not None})
    return result


def app_safe_company_profiles(profiles: list[dict]) -> list[dict]:
    """Supply the required compatibility fields expected by released app builds."""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    safe_profiles = []
    for profile in profiles:
        item = dict(profile)
        item.setdefault("source", item.get("tickerResolutionSource") or "SEC Form 13F")
        item.setdefault("status", "identified")
        item.setdefault("updatedAt", now)
        safe_profiles.append(item)
    return safe_profiles


def sanitize_company_profile(profile: dict) -> dict:
    """Prevent stale or non-equity market metrics from entering the app or score."""
    item = dict(profile)
    warnings = list(item.get("metricWarnings") or [])
    if item.get("quoteEligible") is False:
        for key in MARKET_PROFILE_FIELDS:
            item[key] = None
        item["paysDividend"] = None
        warnings.append("NON_EQUITY_OR_UNQUOTED_INSTRUMENT")
    dividend_yield = item.get("dividendYield")
    if dividend_yield is not None and not 0 <= dividend_yield <= 0.20:
        item["dividendYield"] = None
        warnings.append("DIVIDEND_YIELD_OUT_OF_RANGE")
    pe = item.get("peRatio")
    if pe is not None and pe <= 0:
        item["peRatio"] = None
        warnings.append("PE_NOT_MEANINGFUL")
    if warnings:
        item["metricWarnings"] = sorted(set(warnings))
    return item


def graduated_score(value: float, points: list[tuple[float, float]]) -> int:
    """Linearly interpolate a score so adjacent values do not create abrupt jumps."""
    if value <= points[0][0]:
        return round(points[0][1])
    for (left_x, left_y), (right_x, right_y) in zip(points, points[1:]):
        if value <= right_x:
            progress = (value - left_x) / (right_x - left_x)
            return round(left_y + progress * (right_y - left_y))
    return round(points[-1][1])


def yield_investor_score(dividend_yield: float | None) -> int:
    if dividend_yield is None or dividend_yield <= 0:
        return 0
    return graduated_score(dividend_yield, [
        (0, 0), (1, 0), (2, 2), (3, 6), (3.5, 9), (4, 14),
        (5, 18), (5.5, 20), (6, 22), (6.5, 22), (7, 20),
        (8, 17), (9, 13), (10, 8), (12, 4), (15, 0), (20, 0),
    ])


def reweight_dividend_growth_score(points: int, previous_maximum: int = 8) -> int:
    """Rescale existing eligible points with half-up rounding; preserve zero."""
    if previous_maximum <= 0:
        raise ValueError("Dividend growth maximum must be positive")
    bounded = max(0, min(previous_maximum, points))
    return min(DIVIDEND_GROWTH_SCORE_MAXIMUM,
               (2 * bounded * DIVIDEND_GROWTH_SCORE_MAXIMUM + previous_maximum) // (2 * previous_maximum))


def valuation_investor_score(pe: float | None, ideal_pe: float | None) -> int:
    """Strict 35-point P/E scale; sector context may penalize, never inflate.

    Low P/E is a valuation signal, not proof of business quality. Losses or
    unavailable/non-finite multiples earn no points; build tracks missing data.
    """
    if pe is None or not math.isfinite(pe) or pe <= 0:
        return 0
    base = graduated_score(pe, [
        (5, 35), (8, 35), (10, 30), (12, 24), (15, 16),
        (18, 10), (20, 7), (25, 2), (30, 0),
    ])
    relative = pe / ideal_pe if ideal_pe is not None and math.isfinite(ideal_pe) and ideal_pe > 0 else 1
    penalty = graduated_score(relative, [(1, 0), (1.15, 2), (1.35, 5), (1.65, 8), (2, 12)])
    # Rounding immediately above 8x must not award the maximum.
    maximum = 35 if pe <= 8 else 34
    return max(0, min(maximum, base - penalty))


def consensus_investor_score(counts: dict) -> int:
    """Reward broad ownership and recent conviction, especially new positions."""
    holders_score = min(3, counts.get("holders", 0))
    buying_score = min(2, counts.get("buying", 0))
    new_position_score = min(2, counts.get("newPositions", 0))
    selling_penalty = min(2, counts.get("selling", 0))
    return max(0, min(7, holders_score + buying_score + new_position_score - selling_penalty))


def debt_to_earnings_investor_score(debt_to_earnings: float | None, *, loss_making: bool = False) -> int:
    """Reward balance-sheet resilience using debt relative to annual earnings."""
    if loss_making:
        return 0
    if debt_to_earnings is None:
        return 0
    return graduated_score(max(0, debt_to_earnings), [
        (0, 10), (1, 9), (2, 8), (3, 6), (4, 4), (5, 2), (6, 0), (10, 0),
    ])


def moving_average_investor_score(price_vs_average_percent: float | None) -> int:
    """Reward prices below the verified 1,000-session moving average."""
    if price_vs_average_percent is None:
        return 0
    return graduated_score(price_vs_average_percent, [
        (-50, 6), (-25, 6), (-15, 5), (-5, 4), (0, 3),
        (10, 2), (25, 1), (40, 0), (100, 0),
    ])


def operating_margin_investor_score(operating_margin: float | None) -> int:
    """Strict 0–10 rating: weak margins earn little; 30% earns full credit.

    The component retains its 12/100 weight. Missing data is separately
    marked incomplete by build(); losses and margins <=5% earn zero.
    """
    if operating_margin is None:
        return 0
    rating = graduated_score(operating_margin, [
        (0, 0), (5, 0), (10, 2), (15, 4), (20, 6), (25, 8), (30, 10),
    ])
    return min(9, rating) if operating_margin < 30 else 10


def quality_investor_score(summary: dict) -> dict:
    """Score business quality from the annual metrics that are actually available.

    The 12-point component combines operating margin (4), ROCE (3), net
    margin (3), and cash conversion (2). At least two metrics are required.
    Missing weights are not redistributed and coverage remains explicit.
    """
    net_income = summary.get("netIncome")
    cash_from_operations = summary.get("cashFromOperations")
    cash_conversion = None
    if net_income is not None and cash_from_operations is not None:
        cash_conversion = 0 if net_income <= 0 else cash_from_operations / net_income

    definitions = (
        ("operatingMargin", summary.get("operatingMargin"), 4,
         [(-10, 0), (5, 0), (10, 1), (15, 2), (20, 3), (25, 4)]),
        ("roce", summary.get("roce"), 3,
         [(-10, 0), (5, 0), (10, 1), (15, 2), (20, 3)]),
        ("netMargin", summary.get("netMargin"), 3,
         [(-10, 0), (3, 0), (8, 1), (12, 2), (18, 3)]),
        ("cashConversion", cash_conversion, 2,
         [(0, 0), (0.6, 0), (0.9, 1), (1.1, 2)]),
    )
    components = {}
    available_count = 0
    available_maximum = 0
    score = 0
    for name, value, maximum, scale in definitions:
        available = value is not None and math.isfinite(float(value))
        component_score = graduated_score(float(value), scale) if available else 0
        component_score = max(0, min(maximum, component_score))
        components[name] = {
            "score": component_score,
            "maximum": maximum,
            "available": available,
            "value": round(float(value), 3) if available else None,
        }
        if available:
            available_count += 1
            available_maximum += maximum
            score += component_score

    usable = available_count >= 2
    if not usable:
        available_maximum = 0
        score = 0
    return {
        "score": min(QUALITY_SCORE_MAXIMUM, score),
        "availableMaximum": available_maximum,
        "coverage": round(available_maximum / QUALITY_SCORE_MAXIMUM * 100),
        "status": (
            "COMPLETE" if available_maximum == QUALITY_SCORE_MAXIMUM
            else "PARTIAL" if usable
            else "MISSING"
        ),
        "components": components,
    }


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


def compact_company_reports(reports: list[dict]) -> list[dict]:
    """Store repeated XBRL history once while keeping every report summary."""
    allowed = [
        report for report in reports
        if str(report.get("form", "")).upper().startswith(("10-K", "20-F", "40-F", "10-Q"))
    ]
    annual_by_cusip: dict[str, list[dict]] = defaultdict(list)
    for report in allowed:
        if str(report.get("form", "")).upper().startswith(("10-K", "20-F", "40-F")):
            annual_by_cusip[report.get("cusip", "")].append(report)

    consolidated: dict[str, dict] = {}
    for cusip, annual_reports in annual_by_cusip.items():
        merged: dict[str, dict] = {}
        for report in sorted(annual_reports, key=lambda item: item.get("filingDate", "")):
            for metric, series in (report.get("metrics") or {}).items():
                target = merged.setdefault(metric, {"concept": series.get("concept", metric), "periods": {}})
                for period in series.get("periods", []):
                    key = (period.get("startDate") or "instant") + "-" + period.get("endDate", "")
                    target["periods"][key] = period
        consolidated[cusip] = {
            metric: {
                "concept": series["concept"],
                "periods": sorted(series["periods"].values(), key=lambda period: period.get("endDate", "")),
            }
            for metric, series in merged.items()
        }

    latest_annual = {
        cusip: max(items, key=lambda item: item.get("filingDate", "")).get("accessionNumber")
        for cusip, items in annual_by_cusip.items()
    }
    result = []
    for report in allowed:
        item = {**report}
        item["summary"] = {key: value for key, value in (item.get("summary") or {}).items() if key != "payoutRatio"}
        form = str(item.get("form", "")).upper()
        if form.startswith("10-Q"):
            item["metrics"] = {}
        elif item.get("accessionNumber") == latest_annual.get(item.get("cusip", "")):
            item["metrics"] = consolidated.get(item.get("cusip", ""), {})
        else:
            item["metrics"] = {}
        result.append(item)
    return sorted(
        result,
        key=lambda item: (item["filingDate"], item.get("accessionNumber", ""), item.get("cusip", "")),
        reverse=True,
    )


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


def consensus_rank_key(item: dict) -> str:
    """Return a stable identity for comparing consolidated consensus rows."""
    return issuer_key(item.get("company")) or str(item.get("cusip") or item.get("ticker") or "")


def annotate_opportunity_rank_changes(items: list[dict], previous_items: list[dict] | None = None) -> None:
    """Annotate the scored ranking with its movement since the prior snapshot.

    Positive ``rankChange`` means that the company moved up. Incomplete rows do
    not receive a rank, so finishing a previously incomplete score is treated as
    a new entry instead of an artificial jump from the bottom of the table.
    """
    previous_ranks = {}
    derived_rank = 0
    for previous in previous_items or []:
        if previous.get("opportunityScore") is None:
            continue
        derived_rank += 1
        rank = previous.get("opportunityRank") or derived_rank
        key = consensus_rank_key(previous)
        if key and key not in previous_ranks:
            previous_ranks[key] = rank

    current_rank = 0
    for item in items:
        if item.get("opportunityScore") is None:
            item.update({
                "opportunityRank": None,
                "previousOpportunityRank": previous_ranks.get(consensus_rank_key(item)),
                "rankChange": None,
                "rankStatus": "UNRANKED",
            })
            continue

        current_rank += 1
        previous_rank = previous_ranks.get(consensus_rank_key(item))
        if previous_rank is None:
            rank_change = None
            rank_status = "NEW"
        else:
            rank_change = previous_rank - current_rank
            rank_status = "UP" if rank_change > 0 else "DOWN" if rank_change < 0 else "UNCHANGED"
        item.update({
            "opportunityRank": current_rank,
            "previousOpportunityRank": previous_rank,
            "rankChange": rank_change,
            "rankStatus": rank_status,
        })


def build(current: dict, previous: dict, companies: list[dict], company_profiles: list[dict] | None = None, prior_updates: list[dict] | None = None, average_prices: dict[tuple[str, str], float] | None = None, company_reports: list[dict] | None = None, previous_consensus: list[dict] | None = None) -> dict:
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
    consensus = defaultdict(lambda: {"holders": 0, "buying": 0, "selling": 0, "newPositions": 0})
    issuer_consensus = defaultdict(lambda: {"holders": 0, "buying": 0, "selling": 0, "newPositions": 0})
    consensus_names = {}

    for investor in current.get("investors", []):
        old = old_investors.get(investor["id"], {})
        old_items = aggregate_holdings(old.get("holdings", []))
        current_items = aggregate_holdings(investor.get("holdings", []))
        old_holdings = {item.get("cusip", item["ticker"]): item for item in old_items}
        new_holdings = {item.get("cusip", item["ticker"]): item for item in current_items}
        old_by_issuer = defaultdict(float)
        new_by_issuer = defaultdict(float)
        for item in old_items:
            old_by_issuer[issuer_key(item.get("company") or item.get("ticker"))] += item.get("shares", 0)
        for item in current_items:
            new_by_issuer[issuer_key(item.get("company") or item.get("ticker"))] += item.get("shares", 0)
        for key in old_by_issuer.keys() | new_by_issuer.keys():
            old_shares = old_by_issuer.get(key, 0)
            new_shares = new_by_issuer.get(key, 0)
            action, _ = classify(old_shares, new_shares)
            if new_shares > 0:
                issuer_consensus[key]["holders"] += 1
            if action in ("NEW", "INCREASED"):
                issuer_consensus[key]["buying"] += 1
                if action == "NEW":
                    issuer_consensus[key]["newPositions"] += 1
            elif action in ("SOLD", "REDUCED"):
                issuer_consensus[key]["selling"] += 1
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
                if action == "NEW":
                    consensus[security_id]["newPositions"] += 1
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
    profiles_by_issuer = {}
    for profile_item in company_profiles or []:
        key = issuer_key(profile_item.get("name"))
        if key:
            profiles_by_issuer[key] = merge_known(profiles_by_issuer.get(key, {}), profile_item)
    latest_reports = {}
    latest_reports_by_issuer = {}
    for report in company_reports or []:
        cusip = report.get("cusip")
        if cusip and str(report.get("form", "")).upper().startswith(("10-K", "20-F", "40-F")):
            if cusip not in latest_reports or report.get("filingDate", "") > latest_reports[cusip].get("filingDate", ""):
                latest_reports[cusip] = report
            key = issuer_key(report.get("companyName"))
            if key and (key not in latest_reports_by_issuer or report.get("filingDate", "") > latest_reports_by_issuer[key].get("filingDate", "")):
                latest_reports_by_issuer[key] = report
    for ticker, counts in consensus.items():
        company = company_by_cusip.get(ticker, company_by_ticker.get(ticker, {}))
        display_name = company.get("company", consensus_names.get(ticker, holding_name_by_ticker.get(ticker, ticker)))
        direct_profile = profiles_by_cusip.get(ticker, {})
        profile = merge_known(profiles_by_issuer.get(issuer_key(direct_profile.get("name") or display_name), {}), direct_profile)
        display_name = profile.get("name", display_name)
        report = latest_reports.get(ticker) or latest_reports_by_issuer.get(issuer_key(display_name)) or {}
        dividend_yield = profile.get("dividendYield")
        yield_percent = dividend_yield * 100 if dividend_yield is not None else company.get("yield")
        pe = profile.get("peRatio", company.get("pe"))
        report_summary = report.get("summary") or {}
        operating_margin = report_summary.get("operatingMargin")
        roce = report_summary.get("roce")
        total_debt = report_summary.get("totalDebt")
        cash = report_summary.get("cash")
        net_income = report_summary.get("netIncome")
        net_margin = report_summary.get("netMargin")
        cash_from_operations = report_summary.get("cashFromOperations")
        quality = quality_investor_score(report_summary)
        dividend_periods = ((report.get("metrics") or {}).get("dividendPerShare") or {}).get("periods", [])
        annual_dividends = []
        for period in sorted(dividend_periods, key=lambda item: item.get("endDate", "")):
            value = period.get("value")
            if period.get("fiscalPeriod") == "FY" and value is not None and value > 0:
                annual_dividends.append(float(value))
        if len(annual_dividends) >= 2 and annual_dividends[0] > 0:
            dividend_growth = round(((annual_dividends[-1] / annual_dividends[0]) ** (1 / (len(annual_dividends) - 1)) - 1) * 100, 2)
            dividend_increases = all(current >= previous for previous, current in zip(annual_dividends, annual_dividends[1:]))
        else:
            dividend_growth = company.get("dividendGrowth5Y")
            dividend_increases = dividend_growth is not None and dividend_growth >= 0
        pays_dividend = profile.get("paysDividend")
        if pays_dividend is False:
            yield_percent = 0
            dividend_growth = 0
            dividend_increases = False

        market_price = profile.get("marketPrice")
        moving_average_1000 = profile.get("movingAverage1000")
        price_vs_moving_average_1000 = profile.get("priceVsMovingAverage1000Percent")
        if price_vs_moving_average_1000 is None and market_price is not None and moving_average_1000 is not None and moving_average_1000 > 0:
            price_vs_moving_average_1000 = round((market_price / moving_average_1000 - 1) * 100, 2)
        eps = report_summary.get("epsDiluted") or report_summary.get("eps") or profile.get("eps")
        latest_dividend = annual_dividends[-1] if annual_dividends else profile.get("dividendPerShare")
        pe_was_derived = pe is None and market_price is not None and eps is not None and eps > 0
        if pe_was_derived:
            pe = round(market_price / eps, 2)
        if yield_percent is None and market_price is not None and latest_dividend is not None and latest_dividend >= 0:
            yield_percent = round(latest_dividend / market_price * 100, 2) if market_price > 0 else None

        pe_not_meaningful = pe is None and eps is not None and eps <= 0
        missing_metrics = []
        if yield_percent is None:
            missing_metrics.append("yield")
        if pe is None and not pe_not_meaningful:
            missing_metrics.append("pe")
        if dividend_growth is None:
            missing_metrics.append("dividendGrowth")
        if price_vs_moving_average_1000 is None:
            missing_metrics.append("movingAverage1000")
        quality_missing_names = {
            "operatingMargin": "qualityOperatingMargin",
            "roce": "qualityROCE",
            "netMargin": "qualityNetMargin",
            "cashConversion": "qualityCashConversion",
        }
        for component_name, component in quality["components"].items():
            if not component["available"]:
                missing_metrics.append(quality_missing_names[component_name])
        sector = profile.get("sector", company.get("sector", "Unknown"))
        industry = str(profile.get("industry") or "").lower()
        financial_business = "financial" in str(sector).lower() or any(keyword in industry for keyword in (
            "bank", "insurance", "financial", "capital markets", "asset management",
            "credit services", "mortgage", "brokerage",
        ))
        net_debt = max(0, total_debt - cash) if total_debt is not None and cash is not None else None
        debt_basis = "NET_DEBT_TO_NET_INCOME" if net_debt is not None else "TOTAL_DEBT_TO_NET_INCOME"
        debt_amount = net_debt if net_debt is not None else total_debt
        debt_to_earnings = None
        loss_making_with_debt = debt_amount is not None and debt_amount > 0 and net_income is not None and net_income <= 0
        if debt_amount == 0:
            debt_to_earnings = 0
        elif debt_amount is not None and net_income is not None and net_income > 0:
            debt_to_earnings = round(debt_amount / net_income, 2)
        if financial_business:
            leverage_score = 5
            leverage_status = "NOT_COMPARABLE_FINANCIAL"
        elif loss_making_with_debt:
            leverage_score = 0
            leverage_status = "LOSS_MAKING_WITH_DEBT"
        elif debt_to_earnings is not None:
            leverage_score = debt_to_earnings_investor_score(debt_to_earnings)
            leverage_status = "CALCULATED"
        else:
            leverage_score = 0
            leverage_status = "MISSING"
            missing_metrics.append("debtToEarnings")
        brand_strength = profile.get("brandStrength", "low")
        sector_multiplier = SECTOR_PE_MULTIPLIERS.get(sector, 1.0)
        adjusted_pe_benchmark = round(12 * sector_multiplier * BRAND_MULTIPLIERS.get(brand_strength, 1.0), 1)
        yield_score = yield_investor_score(yield_percent)

        if yield_score == 0:
            growth_score = 0
        elif dividend_growth is None:
            growth_score = 0
        elif dividend_growth < 0 or not dividend_increases:
            growth_score = 0
        elif dividend_growth < 1:
            growth_score = 1
        elif dividend_growth < 3:
            growth_score = 4
        elif dividend_growth < 7:
            growth_score = 7
        else:
            growth_score = 8
        growth_score = reweight_dividend_growth_score(growth_score)
        dividend_score = yield_score + growth_score

        valuation_score = valuation_investor_score(pe, adjusted_pe_benchmark)
        moving_average_score = moving_average_investor_score(price_vs_moving_average_1000)

        operating_margin_rating = operating_margin_investor_score(operating_margin)
        profitability_score = quality["score"]

        consensus_score = consensus_investor_score(counts)
        score = dividend_score + valuation_score + moving_average_score + profitability_score + consensus_score + leverage_score
        available_score_maximum = (
            (22 if yield_percent is not None else 0)
            + (DIVIDEND_GROWTH_SCORE_MAXIMUM if dividend_growth is not None else 0)
            + (35 if pe is not None or pe_not_meaningful else 0)
            + (6 if price_vs_moving_average_1000 is not None else 0)
            + quality["availableMaximum"]
            + (10 if leverage_status != "MISSING" else 0)
            + 7
        )
        score_coverage = round(available_score_maximum / OPPORTUNITY_SCORE_MAXIMUM * 100)
        missing_metrics = sorted(set(missing_metrics))
        consensus_items.append({
            # Older app builds decoded this field as a required String. Keep an
            # empty compatibility value when no real ticker has been verified.
            "ticker": profile.get("ticker") or company.get("ticker") or "",
            "cusip": ticker,
            "company": display_name,
            **counts,
            "yield": yield_percent,
            "pe": pe,
            "peNotMeaningful": pe_not_meaningful,
            "earningsPerShare": eps,
            "peCalculation": "PRICE_OVER_ANNUAL_DILUTED_EPS" if pe_was_derived else "REPORTED",
            "marketPrice": market_price,
            "movingAverage1000": moving_average_1000,
            "priceVsMovingAverage1000Percent": price_vs_moving_average_1000,
            "operatingMargin": operating_margin,
            "roce": roce,
            "netMargin": net_margin,
            "cashFromOperations": cash_from_operations,
            "totalDebt": total_debt,
            "cash": cash,
            "netDebt": net_debt,
            "netIncome": net_income,
            "debtToEarnings": debt_to_earnings,
            "debtRatioBasis": debt_basis if debt_to_earnings is not None else None,
            "leverageInvestorScore": leverage_score,
            "leverageStatus": leverage_status,
            "dividendGrowth": dividend_growth,
            "yieldInvestorScore": yield_score,
            "dividendGrowthInvestorScore": growth_score,
            "dividendGrowthScoreMaximum": DIVIDEND_GROWTH_SCORE_MAXIMUM,
            "opportunityScoreMaximum": OPPORTUNITY_SCORE_MAXIMUM,
            "opportunityScore": min(OPPORTUNITY_SCORE_MAXIMUM, score),
            "scoreStatus": "COMPLETE" if score_coverage == 100 else "PARTIAL",
            "missingScoreMetrics": missing_metrics,
            "scoreCoverage": score_coverage,
            "dividendInvestorScore": dividend_score,
            "valuationInvestorScore": valuation_score,
            "movingAverageInvestorScore": moving_average_score,
            "qualityInvestorScore": profitability_score,
            "qualityScoreMaximum": QUALITY_SCORE_MAXIMUM,
            "qualityCoverage": quality["coverage"],
            "qualityStatus": quality["status"],
            "qualityComponents": quality["components"],
            "profitabilityInvestorScore": profitability_score,
            "operatingMarginRating": operating_margin_rating,
            "consensusInvestorScore": consensus_score,
            "sector": sector,
            "sectorPEBenchmark": adjusted_pe_benchmark,
            "brandPremiumApplied": brand_strength in ("high", "medium"),
        })
    consolidated_items = {}
    for item in consensus_items:
        key = issuer_key(item.get("company")) or item.get("cusip")
        existing = consolidated_items.get(key)
        rank = (item.get("scoreCoverage", 0), item.get("holders", 0))
        existing_rank = (existing.get("scoreCoverage", 0), existing.get("holders", 0)) if existing else (-1, -1)
        if existing is None or rank > existing_rank:
            consolidated_items[key] = item
    consensus_items = []
    for key, item in consolidated_items.items():
        counts = issuer_consensus.get(key, {
            "holders": item["holders"], "buying": item["buying"],
            "selling": item["selling"], "newPositions": item.get("newPositions", 0),
        })
        consensus_score = consensus_investor_score(counts)
        score_without_consensus = (
            item["dividendInvestorScore"] + item["valuationInvestorScore"]
            + item["movingAverageInvestorScore"] + item["profitabilityInvestorScore"]
            + item["leverageInvestorScore"]
        )
        item.update({
            **counts,
            "consensusInvestorScore": consensus_score,
            "opportunityScore": min(OPPORTUNITY_SCORE_MAXIMUM, score_without_consensus + consensus_score),
        })
        consensus_items.append(item)
    consensus_items.sort(key=lambda item: (
        item["opportunityScore"] is not None, item["opportunityScore"] or -1,
        item.get("newPositions", 0), item["buying"], item["holders"],
    ), reverse=True)
    annotate_opportunity_rank_changes(consensus_items, previous_consensus)

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
        public_company = {key: value for key, value in company.items() if key != "payout"}
        opportunities.append({
            **public_company,
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
        "companyProfiles": app_safe_company_profiles(company_profiles or []),
        "companyReports": compact_company_reports(company_reports or []),
    }


def load_fund_portfolios(directory: Path) -> list[dict]:
    """Load the latest verified CNMV report per fund, without inventing trades."""
    latest = {}
    report_ids = set()
    for path in sorted(directory.glob("*/*.json")):
        report = json.loads(path.read_text())
        if report["reportId"] in report_ids:
            raise ValueError(f"Duplicate fund report: {report['reportId']}")
        report_ids.add(report["reportId"])
        if report["reportType"] != "CNMV_SEMIANNUAL" or report["currency"] != "EUR":
            raise ValueError(f"Unsupported fund report: {path}")
        if report["reportDate"] <= report["previousReportDate"]:
            raise ValueError(f"Invalid comparison dates: {path}")
        positions = report["positions"]
        if len({row["isin"] for row in positions}) != len(positions):
            raise ValueError(f"Duplicate ISIN in {path}")
        # Each source cell is rounded to thousands of EUR. Preserve both
        # the stated total and the row values, allowing only rounding error.
        for field, total in (("value", "equityValue"), ("previousValue", "previousEquityValue")):
            if abs(sum(row[field] for row in positions) - report[total]) > len(positions) * 500:
                raise ValueError(f"Unreconciled {field} in {path}")
        for row in positions:
            if row["value"] < 0 or row["previousValue"] < 0:
                raise ValueError(f"Negative holding value: {row['isin']}")
            for value_key, weight_key, assets_key in (
                ("value", "weight", "netAssets"),
                ("previousValue", "previousWeight", "previousNetAssets"),
            ):
                expected = row[value_key] / report[assets_key] * 100
                if abs(row[weight_key] - expected) > 0.02:
                    raise ValueError(f"Invalid weight: {row['isin']}")
            row["status"] = (
                "NEW" if row["value"] > 0 and row["previousValue"] == 0
                else "CLOSED" if row["value"] == 0 and row["previousValue"] > 0
                else "HELD"
            )
            row["weightChangePoints"] = round(row["weight"] - row["previousWeight"], 2)
            # Missing quantity remains missing, never a synthetic zero.
            row["shares"] = None
            row["estimatedAveragePurchasePrice"] = None
            metrics = row.get("metrics")
            if metrics:
                price, dividend = metrics.get("price"), metrics.get("dividendTTM")
                metrics["yieldTTM"] = dividend / price * 100 if price and price > 0 and dividend is not None else None
                metrics["yieldAbove3"] = metrics["yieldTTM"] > 3 if metrics["yieldTTM"] is not None else None
                for key in ("peTrailing", "peForward"):
                    if metrics.get(key) is not None and metrics[key] <= 0:
                        metrics[key] = None
                        metrics[key + "Status"] = "N/M"
        report["positions"] = sorted(positions, key=lambda row: (-row["value"], row["isin"]))
        report["positionCount"] = sum(row["value"] > 0 for row in positions)
        report["newPositions"] = sum(row["status"] == "NEW" for row in positions)
        report["closedPositions"] = sum(row["status"] == "CLOSED" for row in positions)
        prior = latest.get(report["id"])
        if prior is None or report["reportDate"] > prior["reportDate"]:
            latest[report["id"]] = report
    return sorted(latest.values(), key=lambda report: report["name"])


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
    parser.add_argument("--fund-portfolios-directory", type=Path,
                        default=Path(__file__).resolve().parents[1] / "data/fund-portfolios")
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
        # Qualitative research must never overwrite ticker identity, price,
        # yield or P/E. Mixing an old narrative record with a new share class
        # previously produced impossible hybrid metrics.
        qualitative_fields = {key: value for key, value in research.items() if key in QUALITATIVE_PROFILE_FIELDS}
        profiles_by_cusip[research["cusip"]] = merge_known(
            profiles_by_cusip.get(research["cusip"], {}), qualitative_fields
        )
    for settings in valuation:
        profiles_by_cusip[settings["cusip"]] = merge_known(profiles_by_cusip.get(settings["cusip"], {}), settings)
    profiles = sorted((sanitize_company_profile(item) for item in profiles_by_cusip.values()), key=lambda item: item.get("name", ""))
    existing = json.loads(args.output.read_text()) if args.output.exists() else {}
    archived_filings = []
    if args.filings_directory and args.filings_directory.exists():
        archived_filings = [json.loads(path.read_text()) for path in args.filings_directory.glob("*/*.json")]
    company_reports = []
    if args.company_reports_directory and args.company_reports_directory.exists():
        company_reports = [json.loads(path.read_text()) for path in args.company_reports_directory.glob("*/*.json")]
    average_prices = estimate_average_purchase_prices(archived_filings)
    snapshot = build(
        current, previous, companies, profiles, existing.get("filingUpdates", []),
        average_prices, company_reports, existing.get("consensus", []),
    )
    # Non-13F disclosures stay separate: CNMV values are EUR and do not
    # disclose share counts. Never feed their value changes into 13F signals.
    snapshot["dividendEvents"] = existing.get("dividendEvents", [])
    snapshot["fundPortfolios"] = load_fund_portfolios(args.fund_portfolios_directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
