#!/usr/bin/env python3
"""Build the public, app-ready snapshot from normalized quarterly data."""

from __future__ import annotations

import argparse
import json
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
        (0, 0), (1, 0), (2, 2), (3, 7), (3.5, 10), (4, 15),
        (5, 20), (5.5, 22), (6, 24), (6.5, 24), (7, 22),
        (8, 18), (9, 14), (10, 9), (12, 5), (15, 0), (20, 0),
    ])


def valuation_investor_score(pe: float | None, ideal_pe: float) -> int:
    if pe is None:
        return 0
    if pe <= 0:
        return 0
    # Absolute price discipline comes first: only a P/E of 10x or less can
    # receive the maximum valuation score. Sector and brand context can make a
    # modest adjustment, but cannot turn a merely fair multiple into “perfect”.
    base = graduated_score(pe, [
        (5, 45), (10, 45), (12, 41), (15, 34), (18, 27),
        (22, 19), (28, 11), (35, 4), (45, 0),
    ])
    relative = pe / ideal_pe if ideal_pe > 0 else 1
    if relative <= 0.70:
        adjustment = 4
    elif relative <= 0.85:
        adjustment = 3
    elif relative <= 1.00:
        adjustment = 1
    elif relative <= 1.15:
        adjustment = 0
    elif relative <= 1.35:
        adjustment = -3
    else:
        adjustment = -5
    maximum = 45 if pe <= 10 else 44
    return max(0, min(maximum, base + adjustment))


def consensus_investor_score(counts: dict) -> int:
    """Reward broad ownership and recent conviction, especially new positions."""
    holders_score = min(4, counts.get("holders", 0))
    buying_score = min(2, counts.get("buying", 0))
    new_position_score = min(2, counts.get("newPositions", 0))
    selling_penalty = min(2, counts.get("selling", 0))
    return max(0, min(8, holders_score + buying_score + new_position_score - selling_penalty))


def operating_margin_investor_score(operating_margin: float | None) -> int:
    """Score annual operating margin on the user-defined 1–10 ladder."""
    if operating_margin is None:
        return 0
    if operating_margin < 0:
        return 1
    if operating_margin < 3:
        return 2
    if operating_margin < 6:
        return 3
    if operating_margin < 9:
        return 4
    if operating_margin < 12:
        return 5
    if operating_margin < 15:
        return 6
    if operating_margin < 20:
        return 7
    if operating_margin < 25:
        return 8
    if operating_margin < 30:
        return 9
    return 10


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
        if operating_margin is None:
            missing_metrics.append("operatingMargin")
        sector = profile.get("sector", company.get("sector", "Unknown"))
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
            growth_score = 9
        dividend_score = yield_score + growth_score

        valuation_score = valuation_investor_score(pe, adjusted_pe_benchmark)

        operating_margin_rating = operating_margin_investor_score(operating_margin)
        profitability_score = round(operating_margin_rating * 14 / 10)

        consensus_score = consensus_investor_score(counts)
        score = dividend_score + valuation_score + profitability_score + consensus_score
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
            "operatingMargin": operating_margin,
            "roce": roce,
            "dividendGrowth": dividend_growth,
            "yieldInvestorScore": yield_score,
            "dividendGrowthInvestorScore": growth_score,
            "opportunityScore": min(100, score) if not missing_metrics else None,
            "scoreStatus": "COMPLETE" if not missing_metrics else "INCOMPLETE",
            "missingScoreMetrics": missing_metrics,
            "scoreCoverage": round((4 - len(missing_metrics)) / 4 * 100),
            "dividendInvestorScore": dividend_score,
            "valuationInvestorScore": valuation_score,
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
            + item["profitabilityInvestorScore"]
        )
        item.update({
            **counts,
            "consensusInvestorScore": consensus_score,
            "opportunityScore": min(100, score_without_consensus + consensus_score) if item["scoreStatus"] == "COMPLETE" else None,
        })
        consensus_items.append(item)
    consensus_items.sort(key=lambda item: (
        item["opportunityScore"] is not None, item["opportunityScore"] or -1,
        item.get("newPositions", 0), item["buying"], item["holders"],
    ), reverse=True)

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
    snapshot = build(current, previous, companies, profiles, existing.get("filingUpdates", []), average_prices, company_reports)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
