#!/usr/bin/env python3
"""Create a transparent audit of every metric that blocks a dividend score."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def build_audit(snapshot: dict) -> dict:
    items = snapshot.get("consensus", [])
    incomplete = [item for item in items if item.get("opportunityScore") is None]
    profiles = {item.get("cusip"): item for item in snapshot.get("companyProfiles", [])}
    missing_counts = Counter(metric for item in incomplete for metric in item.get("missingScoreMetrics", []))
    combinations = Counter(" + ".join(item.get("missingScoreMetrics", [])) or "none" for item in incomplete)
    def link_status(item: dict) -> str:
        profile = profiles.get(item.get("cusip"))
        if profile is None:
            return "NO_LINKED_PROFILE"
        if not profile.get("ticker"):
            return "NO_VERIFIED_TICKER"
        return "VERIFIED_TICKER_MISSING_METRICS"
    blocking_categories = Counter(link_status(item) for item in incomplete)
    return {
        "generatedAt": snapshot.get("generatedAt"),
        "totalCompanies": len(items),
        "companiesWithCompleteScore": len(items) - len(incomplete),
        "companiesWithoutCompleteScore": len(incomplete),
        "missingByMetric": dict(missing_counts.most_common()),
        "blockingCategories": dict(blocking_categories.most_common()),
        "mostFrequentMissingCombinations": [
            {"metrics": key.split(" + ") if key != "none" else [], "companies": count}
            for key, count in combinations.most_common()
        ],
        "companies": [{
            "company": item.get("company"),
            "cusip": item.get("cusip"),
            "scoreCoverage": item.get("scoreCoverage"),
            "dataLinkStatus": link_status(item),
            "missingMetrics": item.get("missingScoreMetrics", []),
            "availableMetrics": {
                "yield": item.get("yield"),
                "pe": item.get("pe"),
                "earningsPerShare": item.get("earningsPerShare"),
                "peNotMeaningful": item.get("peNotMeaningful", False),
                "operatingMargin": item.get("operatingMargin"),
                "dividendGrowth": item.get("dividendGrowth"),
            },
        } for item in sorted(incomplete, key=lambda value: (value.get("scoreCoverage", 0), value.get("company", "")))],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit = build_audit(json.loads(args.snapshot.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
