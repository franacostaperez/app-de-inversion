#!/usr/bin/env python3
"""Archive company reports and extract comparable financial facts from SEC XBRL."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any

DATA_BASE = "https://data.sec.gov"
ARCHIVE_BASE = "https://www.sec.gov/Archives/edgar/data"
FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A", "10-Q", "10-Q/A"}
EXTRACTION_VERSION = 4

CONCEPTS = {
    # `Revenues` must precede contract-only revenue. REITs and other issuers can
    # report a small ancillary contract amount alongside their much larger
    # consolidated rental/operating revenue.
    "revenue": ("Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerExcludingAssessedTax"),
    "costOfRevenue": ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"),
    "operatingExpenses": ("OperatingExpenses", "CostsAndExpenses"),
    "grossProfit": ("GrossProfit",),
    "operatingIncome": ("OperatingIncomeLoss",),
    "netIncome": ("NetIncomeLoss", "ProfitLoss"),
    "interestExpense": ("InterestExpenseNonOperating", "InterestExpense"),
    "cashFromOperations": ("NetCashProvidedByUsedInOperatingActivities",),
    "capitalExpenditure": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "cash": ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
    "totalAssets": ("Assets",),
    "totalLiabilities": ("Liabilities",),
    "currentLiabilities": ("LiabilitiesCurrent",),
    "shareholdersEquity": ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
    "reportedTotalDebt": (
        "DebtLongtermAndShorttermCombinedAmount",
        "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
        "LongTermDebtAndFinanceLeaseObligationsIncludingCurrentMaturities",
    ),
    "debtCurrent": ("LongTermDebtAndFinanceLeaseObligationsCurrent", "LongTermDebtCurrent", "ShortTermBorrowings"),
    "debtNoncurrent": ("LongTermDebtAndFinanceLeaseObligationsNoncurrent", "LongTermDebtNoncurrent"),
    "longTermDebtTotal": ("LongTermDebtAndFinanceLeaseObligations", "LongTermDebt"),
    "epsDiluted": ("EarningsPerShareDiluted",),
    "dividendPerShare": ("CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid"),
    "dividendsPaid": ("PaymentsOfDividendsCommonStock", "PaymentsOfDividends", "PaymentsOfOrdinaryDividends"),
}

IFRS_CONCEPTS = {
    "revenue": ("Revenue", "RevenueFromContractsWithCustomers"),
    "costOfRevenue": ("CostOfSales",),
    "operatingExpenses": ("DistributionCosts", "AdministrativeExpense"),
    "grossProfit": ("GrossProfit",),
    "operatingIncome": ("ProfitLossFromOperatingActivities", "OperatingProfitLoss"),
    "netIncome": ("ProfitLoss",),
    "interestExpense": ("FinanceCosts",),
    "cashFromOperations": ("CashFlowsFromUsedInOperatingActivities",),
    "capitalExpenditure": ("PurchaseOfPropertyPlantAndEquipment",),
    "cash": ("CashAndCashEquivalents",),
    "totalAssets": ("Assets",),
    "totalLiabilities": ("Liabilities",),
    "currentLiabilities": ("CurrentLiabilities",),
    "shareholdersEquity": ("Equity", "EquityAttributableToOwnersOfParent"),
    "debtCurrent": ("CurrentBorrowings",),
    "debtNoncurrent": ("NoncurrentBorrowings",),
    "epsDiluted": ("DilutedEarningsLossPerShare",),
    "dividendPerShare": (
        "DividendsPerShare", "DividendsPaidOrdinarySharesPerShare",
        "DividendsRecognisedAsDistributionsToOwnersPerShare",
    ),
    "dividendsPaid": ("DividendsPaid", "DividendsPaidClassifiedAsFinancingActivities"),
}


def cutoff(today: date | None = None, years: int = 3) -> date:
    today = today or date.today()
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        return today.replace(year=today.year - years, day=28)


def merge_known(base: dict, preferred: dict) -> dict:
    result = dict(base)
    result.update({key: value for key, value in preferred.items() if value is not None})
    return result


class SecClient:
    def __init__(self, user_agent: str, delay: float = 0.12):
        self.user_agent = user_agent
        self.delay = delay

    def json(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(url, headers={
            "User-Agent": self.user_agent,
            "Accept-Encoding": "identity",
        })
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.load(response)
        time.sleep(self.delay)
        return payload


def recent_rows(submissions: dict[str, Any]) -> list[dict[str, str]]:
    recent = submissions.get("filings", {}).get("recent", {})
    keys = ("accessionNumber", "filingDate", "reportDate", "form", "primaryDocument")
    if not all(key in recent for key in keys):
        return []
    rows = [dict(zip(keys, values)) for values in zip(*(recent[key] for key in keys))]
    return [row for row in rows if row["form"] in FORMS and date.fromisoformat(row["filingDate"]) >= cutoff()]


def fact_rows(companyfacts: dict[str, Any], accession: str, concepts: tuple[str, ...]) -> tuple[str | None, list[dict]]:
    return namespace_fact_rows(companyfacts, accession, "us-gaap", concepts)


def namespace_fact_rows(
    companyfacts: dict[str, Any], accession: str, namespace: str, concepts: tuple[str, ...]
) -> tuple[str | None, list[dict]]:
    taxonomy = companyfacts.get("facts", {}).get(namespace, {})
    for concept in concepts:
        fact = taxonomy.get(concept)
        if not fact:
            continue
        preferred_unit = "USD/shares" if concept in {
            "EarningsPerShareDiluted", "CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid"
        } else "USD"
        units = fact.get("units", {})
        values = units.get(preferred_unit) or next(iter(units.values()), [])
        matches = []
        seen = set()
        for value in values:
            if value.get("accn") != accession or value.get("val") is None:
                continue
            key = (value.get("start"), value.get("end"), value.get("val"))
            if key in seen:
                continue
            seen.add(key)
            matches.append({
                "startDate": value.get("start"),
                "endDate": value.get("end"),
                "value": value["val"],
                "unit": preferred_unit,
                "fiscalYear": value.get("fy"),
                "fiscalPeriod": value.get("fp"),
                "frame": value.get("frame"),
            })
        if matches:
            matches.sort(key=lambda item: (item.get("endDate") or "", item.get("startDate") or ""))
            return concept, matches
    return None, []


def synthesized_metric(concept: str, periods: list[dict]) -> dict:
    return {"concept": concept, "periods": sorted(periods, key=lambda item: item.get("endDate") or "")}


def period_values(metric: dict | None) -> dict[tuple[str | None, str | None], dict]:
    return {
        (period.get("startDate"), period.get("endDate")): period
        for period in (metric or {}).get("periods", [])
        if period.get("value") is not None
    }


def synthesize_income_statement(metrics: dict[str, dict]) -> None:
    """Reconstruct standard subtotals only when the XBRL arithmetic is unambiguous."""
    if "revenue" not in metrics and "grossProfit" in metrics and "costOfRevenue" in metrics:
        gross, costs = period_values(metrics["grossProfit"]), period_values(metrics["costOfRevenue"])
        periods = [{**gross[key], "value": gross[key]["value"] + costs[key]["value"]} for key in gross.keys() & costs.keys()]
        if periods:
            metrics["revenue"] = synthesized_metric("GrossProfitPlusCostOfRevenue", periods)

    if "operatingIncome" in metrics or "operatingExpenses" not in metrics:
        return
    expenses = period_values(metrics["operatingExpenses"])
    expense_concept = metrics["operatingExpenses"].get("concept")
    if expense_concept not in {"CostsAndExpenses", "OperatingExpenses"}:
        return
    base_key = "revenue" if expense_concept == "CostsAndExpenses" else "grossProfit"
    base = period_values(metrics.get(base_key))
    periods = [{**base[key], "value": base[key]["value"] - expenses[key]["value"]} for key in base.keys() & expenses.keys()]
    if periods:
        metrics["operatingIncome"] = synthesized_metric(
            "RevenueLessCostsAndExpenses" if base_key == "revenue" else "GrossProfitLessOperatingExpenses",
            periods,
        )


def latest_value(metrics: dict[str, dict], key: str):
    series = metrics.get(key, {}).get("periods", [])
    return series[-1]["value"] if series else None


def safe_margin(numerator, denominator, maximum_absolute: float | None = None):
    if numerator is None or not denominator:
        return None
    result = round(numerator / denominator * 100, 2)
    if maximum_absolute is not None and abs(result) > maximum_absolute:
        return None
    return result


def synthesize_total_debt(metrics: dict[str, dict]) -> None:
    combined = {}
    for key in ("debtCurrent", "debtNoncurrent"):
        for period in metrics.get(key, {}).get("periods", []):
            combined.setdefault(period["endDate"], {**period, "value": 0})
            combined[period["endDate"]]["value"] += period["value"]
    if "reportedTotalDebt" in metrics:
        metrics["totalDebt"] = metrics["reportedTotalDebt"]
    elif combined and "debtCurrent" in metrics and "debtNoncurrent" in metrics:
        metrics["totalDebt"] = {"concept": "DebtCurrentPlusNoncurrent", "periods": sorted(combined.values(), key=lambda item: item["endDate"])}
    elif "longTermDebtTotal" in metrics:
        metrics["totalDebt"] = metrics["longTermDebtTotal"]


def comparable_growth(metric: dict | None) -> float | None:
    periods = (metric or {}).get("periods", [])
    if len(periods) < 2 or not periods[-1].get("startDate"):
        return None
    latest = periods[-1]
    latest_days = (datetime.fromisoformat(latest["endDate"]) - datetime.fromisoformat(latest["startDate"])).days
    candidates = []
    for period in periods[:-1]:
        if not period.get("startDate") or not period.get("value"):
            continue
        days = (datetime.fromisoformat(period["endDate"]) - datetime.fromisoformat(period["startDate"])).days
        if abs(days - latest_days) <= 20:
            candidates.append(period)
    if not candidates:
        return None
    previous = candidates[-1]["value"]
    return round((latest["value"] / previous - 1) * 100, 2) if previous else None


def build_summary(metrics: dict[str, dict]) -> tuple[dict, str]:
    revenue = latest_value(metrics, "revenue")
    operating_income = latest_value(metrics, "operatingIncome")
    net_income = latest_value(metrics, "netIncome")
    expenses = latest_value(metrics, "operatingExpenses")
    debt = latest_value(metrics, "totalDebt")
    total_assets = latest_value(metrics, "totalAssets")
    current_liabilities = latest_value(metrics, "currentLiabilities")
    dividends_paid = latest_value(metrics, "dividendsPaid")
    dividend_per_share = latest_value(metrics, "dividendPerShare")
    eps_diluted = latest_value(metrics, "epsDiluted")
    if expenses is None and revenue is not None and operating_income is not None:
        expenses = revenue - operating_income
    summary = {
        "revenue": revenue,
        "expenses": expenses,
        "operatingIncome": operating_income,
        "netIncome": net_income,
        # An operating margin outside ±100% usually means the selected XBRL
        # revenue is only an ancillary line and is not comparable to operating
        # income. Quarantine it rather than awarding a perfect score.
        "operatingMargin": safe_margin(operating_income, revenue, maximum_absolute=100),
        "roce": safe_margin(
            operating_income,
            total_assets - current_liabilities
            if total_assets is not None and current_liabilities is not None
            else None,
        ),
        "netMargin": safe_margin(net_income, revenue),
        "totalDebt": debt,
        "cash": latest_value(metrics, "cash"),
        "cashFromOperations": latest_value(metrics, "cashFromOperations"),
        "capitalExpenditure": latest_value(metrics, "capitalExpenditure"),
        "dividendsPaid": dividends_paid,
        "dividendPerShare": dividend_per_share,
        "epsDiluted": eps_diluted,
        "expectedRevenue": None,
        "expectedEPS": None,
    }
    highlights = []
    if revenue is not None:
        highlights.append("Ingresos y comparativas temporales extraídos del XBRL del informe.")
    revenue_growth = comparable_growth(metrics.get("revenue"))
    income_growth = comparable_growth(metrics.get("netIncome"))
    if revenue_growth is not None:
        highlights.append(f"Los ingresos variaron un {revenue_growth:+.1f}% frente al periodo comparable.")
    if income_growth is not None:
        highlights.append(f"El beneficio neto varió un {income_growth:+.1f}% frente al periodo comparable.")
    if summary["netMargin"] is not None:
        highlights.append(f"El margen neto del periodo más reciente es {summary['netMargin']:.1f}%.")
    if summary["roce"] is not None:
        highlights.append(f"El ROCE estimado del periodo más reciente es {summary['roce']:.1f}%.")
    if debt is not None:
        highlights.append("La deuda declarada queda incorporada para seguir su evolución.")
    if summary["cashFromOperations"] is not None:
        highlights.append("Incluye generación de caja operativa y, cuando está disponible, inversión de capital.")
    return summary, " ".join(highlights) or "Informe archivado; algunas métricas no están estandarizadas en XBRL."


def archive_url(cik: int, accession: str, document: str) -> str:
    return f"{ARCHIVE_BASE}/{cik}/{accession.replace('-', '')}/{document}"


def extract_report(profile: dict, cik: int, row: dict[str, str], companyfacts: dict) -> dict:
    metrics = {}
    for key, concepts in CONCEPTS.items():
        concept, periods = fact_rows(companyfacts, row["accessionNumber"], concepts)
        if not periods:
            concept, periods = namespace_fact_rows(
                companyfacts, row["accessionNumber"], "ifrs-full", IFRS_CONCEPTS.get(key, ())
            )
        if periods:
            metrics[key] = {"concept": concept, "periods": periods}
    synthesize_income_statement(metrics)
    synthesize_total_debt(metrics)
    summary, narrative = build_summary(metrics)
    return {
        "cusip": profile["cusip"],
        "ticker": profile.get("ticker"),
        "companyName": profile.get("name", profile.get("ticker", "Empresa")),
        "cik": str(cik),
        "accessionNumber": row["accessionNumber"],
        "form": row["form"],
        "filingDate": row["filingDate"] + "T00:00:00Z",
        "reportDate": row["reportDate"] + "T00:00:00Z",
        "secURL": archive_url(cik, row["accessionNumber"], row["primaryDocument"]),
        "source": "SEC EDGAR XBRL",
        "extractionVersion": EXTRACTION_VERSION,
        "summary": summary,
        "highlights": narrative,
        "metrics": metrics,
    }


def ticker_ciks(payload: dict) -> dict[str, int]:
    return {item["ticker"].upper(): int(item["cik_str"]) for item in payload.values()}


def run(client: SecClient, profiles: list[dict], output: Path, refresh: bool = False) -> int:
    mapping = ticker_ciks(client.json("https://www.sec.gov/files/company_tickers.json"))
    written = 0
    for profile in profiles:
        ticker = str(profile.get("ticker") or "").upper()
        profile_cik = str(profile.get("sp500Cik") or "").strip()
        cik = int(profile_cik) if profile_cik.isdigit() else mapping.get(ticker)
        if not cik:
            continue
        submissions = client.json(f"{DATA_BASE}/submissions/CIK{cik:010d}.json")
        rows = recent_rows(submissions)
        missing = []
        for row in rows:
            destination = output / profile["cusip"] / f"{row['accessionNumber']}.json"
            needs_derived_metrics = False
            if destination.exists() and not refresh:
                try:
                    stored = json.loads(destination.read_text())
                    summary = stored.get("summary", {})
                    needs_derived_metrics = (
                        stored.get("extractionVersion", 0) < EXTRACTION_VERSION
                        or "operatingMargin" not in summary
                        or "epsDiluted" not in summary
                    )
                except (OSError, json.JSONDecodeError):
                    needs_derived_metrics = True
            if refresh or not destination.exists() or needs_derived_metrics:
                missing.append(row)
        if not missing:
            continue
        facts = client.json(f"{DATA_BASE}/api/xbrl/companyfacts/CIK{cik:010d}.json")
        for row in missing:
            destination = output / profile["cusip"] / f"{row['accessionNumber']}.json"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(extract_report(profile, cik, row, facts), indent=2, ensure_ascii=False) + "\n")
            written += 1
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company-database", type=Path, required=True)
    parser.add_argument("--qualitative-database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--user-agent", default=os.environ.get("SEC_USER_AGENT"))
    args = parser.parse_args()
    if not args.user_agent or "@" not in args.user_agent:
        parser.error("Set SEC_USER_AGENT to an identifiable value containing an email address")
    base = json.loads(args.company_database.read_text()) if args.company_database.exists() else []
    qualitative = json.loads(args.qualitative_database.read_text()) if args.qualitative_database.exists() else []
    profiles = {item["cusip"]: item for item in base}
    for item in qualitative:
        profiles[item["cusip"]] = merge_known(profiles.get(item["cusip"], {}), item)
    written = run(SecClient(args.user_agent), list(profiles.values()), args.output, args.refresh)
    print(f"Archived {written} new company reports")


if __name__ == "__main__":
    main()
