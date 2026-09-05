#!/usr/bin/env python3
"""Audit every app metric for unit, source and calculation consistency."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def numeric(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def normalized_yield(value):
    value = numeric(value)
    if value is None or value < 0:
        return None
    if 0.20 < value <= 20:
        value /= 100
    return value if value <= 0.20 else None


def add_issue(issues: list[dict], item: dict, code: str, severity: str, details: dict) -> None:
    issues.append({
        "company": item.get("name") or item.get("company"),
        "cusip": item.get("cusip"),
        "ticker": item.get("ticker") or None,
        "code": code,
        "severity": severity,
        "details": details,
    })


def build_metric_audit(snapshot: dict) -> dict:
    profiles = snapshot.get("companyProfiles", [])
    company_scores = snapshot.get("companyScores") or []
    scores = company_scores or snapshot.get("consensus", [])
    issues: list[dict] = []
    market_fields = ("marketPrice", "dividendYield", "dividendPerShare", "peRatio", "eps")

    for item in profiles:
        metric_warnings = set(item.get("metricWarnings") or [])
        if item.get("quoteEligible") is False and any(item.get(key) is not None for key in market_fields):
            add_issue(issues, item, "NON_EQUITY_HAS_MARKET_METRICS", "error", {
                key: item.get(key) for key in market_fields if item.get(key) is not None
            })
        dividend_yield = normalized_yield(item.get("dividendYield"))
        if item.get("dividendYield") is not None and dividend_yield is None:
            add_issue(issues, item, "YIELD_OUT_OF_RANGE", "error", {"yield": item.get("dividendYield")})
        google_yield = normalized_yield(item.get("googleDividendYield"))
        yahoo_yield = normalized_yield(item.get("yahooDividendYield"))
        if google_yield is not None and yahoo_yield is not None:
            difference = abs(google_yield - yahoo_yield)
            handled_yield_conflict = any(code in metric_warnings for code in (
                "MARKET_YIELD_CONFLICT_RESOLVED_BY_DIVIDEND_RATE",
                "MARKET_YIELD_PROVIDER_CONFLICT",
            ))
            if difference > max(0.005, max(google_yield, yahoo_yield) * 0.25) and not handled_yield_conflict:
                add_issue(issues, item, "YIELD_PROVIDER_CONFLICT", "error", {
                    "googlePercent": round(google_yield * 100, 3),
                    "yahooPercent": round(yahoo_yield * 100, 3),
                })
        price = numeric(item.get("marketPrice"))
        dividend = numeric(item.get("dividendPerShare"))
        if price and dividend is not None and dividend_yield is not None:
            calculated = dividend / price
            if abs(calculated - dividend_yield) > max(0.006, dividend_yield * 0.30):
                add_issue(issues, item, "YIELD_DIFFERS_FROM_DIVIDEND_OVER_PRICE", "warning", {
                    "reportedPercent": round(dividend_yield * 100, 3),
                    "calculatedPercent": round(calculated * 100, 3),
                    "price": price,
                    "dividendPerShare": dividend,
                })
        if item.get("paysDividend") is False and ((dividend_yield or 0) > 0 or (dividend or 0) > 0):
            add_issue(issues, item, "DIVIDEND_FLAG_CONFLICT", "error", {
                "paysDividend": False, "yield": dividend_yield, "dividendPerShare": dividend,
            })
        google_pe = numeric(item.get("googlePeRatio"))
        yahoo_pe = numeric(item.get("yahooPeRatio"))
        handled_pe_conflict = any(code in metric_warnings for code in (
            "MARKET_PE_CONFLICT_RESOLVED_BY_PRICE_OVER_EPS",
            "MARKET_PE_PROVIDER_CONFLICT",
        ))
        if google_pe and yahoo_pe and abs(google_pe - yahoo_pe) / max(google_pe, yahoo_pe) > 0.35 and not handled_pe_conflict:
            add_issue(issues, item, "PE_PROVIDER_CONFLICT", "error", {
                "google": google_pe, "yahoo": yahoo_pe,
            })
        pe = numeric(item.get("peRatio"))
        eps = numeric(item.get("eps"))
        if price and eps and eps > 0 and pe and abs(price / eps - pe) / max(pe, price / eps) > 0.35:
            add_issue(issues, item, "PE_DIFFERS_FROM_PRICE_OVER_EPS", "warning", {
                "reported": pe, "calculated": round(price / eps, 2), "price": price, "eps": eps,
            })
        average = numeric(item.get("movingAverage1000"))
        relative = numeric(item.get("priceVsMovingAverage1000Percent"))
        if price and average and relative is not None and abs((price / average - 1) * 100 - relative) > 0.2:
            add_issue(issues, item, "MOVING_AVERAGE_CALCULATION_CONFLICT", "error", {
                "reportedPercent": relative, "calculatedPercent": round((price / average - 1) * 100, 2),
            })

    seen_issuers: dict[str, dict] = {}
    for item in scores:
        margin = numeric(item.get("operatingMargin"))
        if margin is not None and abs(margin) > 100:
            add_issue(issues, item, "OPERATING_MARGIN_OUT_OF_RANGE", "error", {"operatingMargin": margin})
        components = [numeric(item.get(key)) or 0 for key in (
            "dividendInvestorScore", "valuationInvestorScore", "movingAverageInvestorScore",
            "profitabilityInvestorScore", "consensusInvestorScore", "leverageInvestorScore"
        )]
        score = numeric(item.get("opportunityScore"))
        if score is not None and abs(min(item.get("opportunityScoreMaximum", 100), sum(components)) - score) > 0.01:
            add_issue(issues, item, "SCORE_COMPONENTS_DO_NOT_SUM", "error", {
                "score": score, "componentsTotal": sum(components),
            })
        # Different listed share classes can legitimately share an issuer name.
        # The legacy institutional consensus should still be consolidated by issuer.
        if not company_scores:
            key = "".join(ch for ch in (item.get("company") or "").lower() if ch.isalnum())
            if key and key in seen_issuers:
                add_issue(issues, item, "DUPLICATE_CONSENSUS_ISSUER", "error", {
                    "otherCusip": seen_issuers[key].get("cusip"),
                })
            elif key:
                seen_issuers[key] = item

    by_code = Counter(issue["code"] for issue in issues)
    by_severity = Counter(issue["severity"] for issue in issues)
    warnings_in_profiles = Counter(
        warning
        for profile in profiles
        for warning in (profile.get("metricWarnings") or [])
    )
    return {
        "generatedAt": snapshot.get("generatedAt"),
        "profilesAudited": len(profiles),
        "scoresAudited": len(scores),
        "issuesRemaining": len(issues),
        "issuesBySeverity": dict(sorted(by_severity.items())),
        "issuesByCode": dict(by_code.most_common()),
        "adjustmentsAppliedByPipeline": dict(warnings_in_profiles.most_common()),
        "issues": sorted(issues, key=lambda value: (
            0 if value["severity"] == "error" else 1, value["code"], value.get("company") or ""
        )),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit = build_metric_audit(json.loads(args.snapshot.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
