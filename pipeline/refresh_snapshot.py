#!/usr/bin/env python3
"""Refresh scoring weights and CNMV without replacing cached SEC data."""

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from .build_snapshot import annotate_opportunity_rank_changes, load_fund_portfolios, operating_margin_investor_score, valuation_investor_score, reweight_dividend_growth_score, DIVIDEND_GROWTH_SCORE_MAXIMUM, OPPORTUNITY_SCORE_MAXIMUM
except ImportError:
    from build_snapshot import annotate_opportunity_rank_changes, load_fund_portfolios, operating_margin_investor_score, valuation_investor_score, reweight_dividend_growth_score, DIVIDEND_GROWTH_SCORE_MAXIMUM, OPPORTUNITY_SCORE_MAXIMUM


def refresh(snapshot, fund_portfolios):
    result = copy.deepcopy(snapshot)
    for row in result["consensus"]:
        rating = operating_margin_investor_score(row.get("operatingMargin"))
        points = round(rating * 12 / 10)
        old_points = row["profitabilityInvestorScore"]
        valuation = valuation_investor_score(row.get("pe"), row.get("sectorPEBenchmark"))
        old_valuation = row["valuationInvestorScore"]
        old_growth = row.get("dividendGrowthInvestorScore", 0)
        growth = reweight_dividend_growth_score(old_growth, row.get("dividendGrowthScoreMaximum", 8))
        # Change only the requested components; missing data stays incomplete.
        if row.get("opportunityScore") is not None:
            row["opportunityScore"] = max(0, min(OPPORTUNITY_SCORE_MAXIMUM, row["opportunityScore"] - old_points + points - old_valuation + valuation - old_growth + growth))
        row["operatingMarginRating"] = rating
        row["profitabilityInvestorScore"] = points
        row["valuationInvestorScore"] = valuation
        row["dividendGrowthInvestorScore"] = growth
        row["dividendInvestorScore"] = row.get("yieldInvestorScore", 0) + growth
        row["dividendGrowthScoreMaximum"] = DIVIDEND_GROWTH_SCORE_MAXIMUM
        row["opportunityScoreMaximum"] = OPPORTUNITY_SCORE_MAXIMUM
    result["consensus"].sort(key=lambda row: (
        row["opportunityScore"] is not None, row["opportunityScore"] or -1,
        row.get("newPositions", 0), row["buying"], row["holders"],
    ), reverse=True)
    annotate_opportunity_rank_changes(result["consensus"], snapshot["consensus"])
    result["fundPortfolios"] = copy.deepcopy(fund_portfolios)
    result["generatedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/public/snapshot.json", help="Snapshot path or - for stdin")
    parser.add_argument("--output", type=Path, default=Path("data/public/snapshot.json"))
    parser.add_argument("--fund-portfolios-directory", type=Path,
                        default=Path(__file__).resolve().parents[1] / "data/fund-portfolios")
    args = parser.parse_args()
    source = json.load(sys.stdin) if args.input == "-" else json.loads(Path(args.input).read_text())
    updated = refresh(source, load_fund_portfolios(args.fund_portfolios_directory))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(updated, ensure_ascii=False, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
