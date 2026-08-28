#!/usr/bin/env python3
"""Refresh margin scores and CNMV portfolios without replacing cached SEC data."""

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from .build_snapshot import annotate_opportunity_rank_changes, load_fund_portfolios, operating_margin_investor_score
except ImportError:
    from build_snapshot import annotate_opportunity_rank_changes, load_fund_portfolios, operating_margin_investor_score


def refresh(snapshot, fund_portfolios):
    result = copy.deepcopy(snapshot)
    for row in result["consensus"]:
        rating = operating_margin_investor_score(row.get("operatingMargin"))
        points = round(rating * 12 / 10)
        old_points = row["profitabilityInvestorScore"]
        # Only the margin component changes. Missing data stays incomplete.
        if row.get("opportunityScore") is not None:
            row["opportunityScore"] = max(0, min(100, row["opportunityScore"] - old_points + points))
        row["operatingMarginRating"] = rating
        row["profitabilityInvestorScore"] = points
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
