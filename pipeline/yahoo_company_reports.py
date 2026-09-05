#!/usr/bin/env python3
"""Build normalized annual financial reports for non-US listed companies."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


USER_AGENT = "Mozilla/5.0 DividendIntelligence/1.0"
EXTRACTION_VERSION = 1
FIELD_MAP = {
    "annualTotalRevenue": "revenue",
    "annualOperatingIncome": "operatingIncome",
    "annualTotalExpenses": "expenses",
    "annualNetIncome": "netIncome",
    "annualOperatingCashFlow": "cashFromOperations",
    "annualCapitalExpenditure": "capitalExpenditure",
    "annualCashCashEquivalentsAndShortTermInvestments": "cash",
    "annualTotalDebt": "totalDebt",
    "annualTotalAssets": "totalAssets",
    "annualCurrentLiabilities": "currentLiabilities",
    "annualStockholdersEquity": "shareholdersEquity",
    "annualDilutedEPS": "epsDiluted",
    "annualBasicEPS": "eps",
    "annualCashDividendsPaid": "dividendsPaid",
    "annualInvestedCapital": "investedCapital",
}
FLOW_METRICS = {
    "revenue", "expenses", "operatingIncome", "netIncome", "cashFromOperations",
    "capitalExpenditure", "dividendsPaid", "epsDiluted", "eps",
}


def safe_margin(numerator, denominator):
    if numerator is None or denominator in (None, 0):
        return None
    value = round(float(numerator) / float(denominator) * 100, 2)
    return value if abs(value) <= 200 else None


def annual_start(end_date: str) -> str:
    end = date.fromisoformat(end_date)
    try:
        prior = end.replace(year=end.year - 1)
    except ValueError:
        prior = end.replace(year=end.year - 1, day=28)
    return (prior + timedelta(days=1)).isoformat()


def extract_series(payload: dict) -> dict[str, dict]:
    metrics: dict[str, dict] = {}
    for series in payload.get("timeseries", {}).get("result") or []:
        source_key = next((key for key in FIELD_MAP if key in series), None)
        if not source_key:
            continue
        metric = FIELD_MAP[source_key]
        periods = []
        for row in series.get(source_key) or []:
            raw = (row.get("reportedValue") or {}).get("raw")
            end_date = row.get("asOfDate")
            if raw is None or not end_date or row.get("periodType") not in (None, "12M"):
                continue
            value = float(raw)
            if metric in {"capitalExpenditure", "dividendsPaid"}:
                value = abs(value)
            periods.append({
                "startDate": annual_start(end_date) if metric in FLOW_METRICS else None,
                "endDate": end_date,
                "value": value,
                "unit": row.get("currencyCode") or ("shares" if metric in {"eps", "epsDiluted"} else None),
                "fiscalYear": int(end_date[:4]),
                "fiscalPeriod": "FY",
            })
        if periods:
            metrics[metric] = {
                "concept": source_key,
                "periods": sorted(periods, key=lambda item: item["endDate"]),
            }
    return metrics


def extract_dividend_series(payload: dict) -> dict | None:
    results = payload.get("chart", {}).get("result") or []
    if not results:
        return None
    result = results[0]
    currency = (result.get("meta") or {}).get("currency")
    annual = defaultdict(float)
    for event in ((result.get("events") or {}).get("dividends") or {}).values():
        timestamp, amount = event.get("date"), event.get("amount")
        if timestamp and amount is not None:
            annual[datetime.fromtimestamp(timestamp, timezone.utc).year] += float(amount)
    periods = [{
        "startDate": f"{year}-01-01",
        "endDate": f"{year}-12-31",
        "value": round(value, 6),
        "unit": currency,
        "fiscalYear": year,
        "fiscalPeriod": "FY",
    } for year, value in sorted(annual.items()) if value > 0]
    return {"concept": "YahooChartCashDividendsPerShare", "periods": periods} if periods else None


def value_on(metrics: dict[str, dict], metric: str, end_date: str):
    for period in metrics.get(metric, {}).get("periods", []):
        if period.get("endDate") == end_date:
            return period.get("value")
    return None


def summary_on(metrics: dict[str, dict], end_date: str) -> dict:
    revenue = value_on(metrics, "revenue", end_date)
    reported_expenses = value_on(metrics, "expenses", end_date)
    operating_income = value_on(metrics, "operatingIncome", end_date)
    net_income = value_on(metrics, "netIncome", end_date)
    total_assets = value_on(metrics, "totalAssets", end_date)
    current_liabilities = value_on(metrics, "currentLiabilities", end_date)
    invested_capital = value_on(metrics, "investedCapital", end_date)
    capital_employed = invested_capital
    if capital_employed in (None, 0) and total_assets is not None and current_liabilities is not None:
        capital_employed = total_assets - current_liabilities
    return {
        "revenue": revenue,
        "expenses": reported_expenses if reported_expenses is not None else (
            revenue - operating_income if revenue is not None and operating_income is not None else None
        ),
        "operatingIncome": operating_income,
        "netIncome": net_income,
        "operatingMargin": safe_margin(operating_income, revenue),
        "roce": safe_margin(operating_income, capital_employed),
        "netMargin": safe_margin(net_income, revenue),
        "totalDebt": value_on(metrics, "totalDebt", end_date),
        "cash": value_on(metrics, "cash", end_date),
        "cashFromOperations": value_on(metrics, "cashFromOperations", end_date),
        "capitalExpenditure": value_on(metrics, "capitalExpenditure", end_date),
        "dividendsPaid": value_on(metrics, "dividendsPaid", end_date),
        "dividendPerShare": None,
        "epsDiluted": value_on(metrics, "epsDiluted", end_date) or value_on(metrics, "eps", end_date),
        "expectedRevenue": None,
        "expectedEPS": None,
    }


def highlights(summary: dict, prior: dict | None = None) -> list[str]:
    result = []
    for label, key in (("Los ingresos", "revenue"), ("El beneficio neto", "netIncome")):
        current, previous = summary.get(key), (prior or {}).get(key)
        if current is not None and previous not in (None, 0):
            change = (current / previous - 1) * 100
            result.append(f"{label} variaron un {change:+.1f}% frente al ejercicio anterior.")
    if summary.get("operatingMargin") is not None:
        result.append(f"El margen operativo del último ejercicio es {summary['operatingMargin']:.1f}%.")
    if summary.get("netMargin") is not None:
        result.append(f"El margen neto del último ejercicio es {summary['netMargin']:.1f}%.")
    if summary.get("roce") is not None:
        result.append(f"El ROCE estimado del último ejercicio es {summary['roce']:.1f}%.")
    return result


class YahooClient:
    def __init__(self, delay: float = 0.35, retries: int = 4):
        self.delay = delay
        self.retries = retries

    def fetch(self, ticker: str, period1: int, period2: int) -> dict:
        encoded = urllib.parse.quote(ticker)
        fields = ",".join(FIELD_MAP)
        path = (
            f"/ws/fundamentals-timeseries/v1/finance/timeseries/{encoded}"
            f"?symbol={encoded}&type={fields}&period1={period1}&period2={period2}"
        )
        last_error = None
        for attempt in range(self.retries):
            host = ("query2.finance.yahoo.com", "query1.finance.yahoo.com")[attempt % 2]
            request = urllib.request.Request("https://" + host + path, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    payload = json.load(response)
                time.sleep(self.delay)
                return payload
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
                last_error = error
                time.sleep(min(8, 1.5 * (attempt + 1)))
        raise RuntimeError(f"Yahoo Finance unavailable for {ticker}: {last_error}")

    def fetch_dividends(self, ticker: str) -> dict:
        encoded = urllib.parse.quote(ticker)
        path = f"/v8/finance/chart/{encoded}?range=6y&interval=1mo&events=div&includeAdjustedClose=true"
        last_error = None
        for attempt in range(self.retries):
            host = ("query2.finance.yahoo.com", "query1.finance.yahoo.com")[attempt % 2]
            request = urllib.request.Request("https://" + host + path, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    payload = json.load(response)
                time.sleep(self.delay)
                return payload
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
                last_error = error
                time.sleep(min(6, attempt + 1))
        raise RuntimeError(f"Yahoo dividend history unavailable for {ticker}: {last_error}")


def reports_for_profile(profile: dict, payload: dict, dividend_payload: dict | None = None) -> list[dict]:
    metrics = extract_series(payload)
    dividend_series = extract_dividend_series(dividend_payload or {})
    if dividend_series:
        metrics["dividendPerShare"] = dividend_series
    report_dates = sorted({
        period["endDate"]
        for series in metrics.values()
        for period in series.get("periods", [])
        if period.get("endDate")
    })
    reports = []
    summaries = {end_date: summary_on(metrics, end_date) for end_date in report_dates}
    for index, end_date in enumerate(report_dates):
        summary = summaries[end_date]
        if sum(value is not None for value in summary.values()) < 2:
            continue
        ticker = profile["ticker"]
        reports.append({
            "cusip": profile["cusip"],
            "ticker": ticker,
            "companyName": profile.get("name", ticker),
            "form": "ANNUAL",
            "filingDate": end_date + "T00:00:00Z",
            "reportDate": end_date + "T00:00:00Z",
            "sourceURL": f"https://finance.yahoo.com/quote/{urllib.parse.quote(ticker)}/financials/",
            "source": "Yahoo Finance · estados financieros anuales normalizados",
            "extractionVersion": EXTRACTION_VERSION,
            "summary": summary,
            "highlights": highlights(summary, summaries.get(report_dates[index - 1]) if index else None),
            "metrics": metrics if index == len(report_dates) - 1 else {},
        })
    return reports


def run(
    profiles: list[dict], client: YahooClient, *, only_ftse100: bool = True, workers: int = 4
) -> tuple[list[dict], list[dict]]:
    period2 = int(time.time()) + 86400
    period1 = period2 - 6 * 366 * 86400
    reports, failures = [], []
    candidates = [profile for profile in profiles if profile.get("ticker")]
    if only_ftse100:
        candidates = [profile for profile in candidates if profile.get("ftse100") is True]
    def fetch_profile(profile: dict):
        try:
            ticker = profile["ticker"]
            fundamentals = client.fetch(ticker, period1, period2)
            dividend_failure = None
            try:
                dividends = client.fetch_dividends(ticker)
            except RuntimeError as error:
                dividends = {}
                dividend_failure = {"ticker": ticker, "reason": str(error), "scope": "dividend history"}
            company_reports = reports_for_profile(profile, fundamentals, dividends)
            if company_reports:
                return company_reports, dividend_failure
            return [], {"ticker": profile["ticker"], "reason": "no annual fundamentals"}
        except RuntimeError as error:
            return [], {"ticker": profile["ticker"], "reason": str(error)}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {executor.submit(fetch_profile, profile): profile for profile in candidates}
        for completed, future in enumerate(as_completed(futures), 1):
            company_reports, failure = future.result()
            reports.extend(company_reports)
            if failure:
                failures.append(failure)
            if completed % 10 == 0 or completed == len(candidates):
                print(f"Processed {completed}/{len(candidates)} FTSE companies", flush=True)
    reports.sort(key=lambda item: (item["ticker"], item["reportDate"]))
    failures.sort(key=lambda item: item["ticker"])
    return reports, failures


def enrich_existing_dividends(
    profiles: list[dict], reports: list[dict], client: YahooClient, *, workers: int = 4
) -> tuple[list[dict], list[dict]]:
    by_ticker = defaultdict(list)
    for report in reports:
        by_ticker[report.get("ticker")].append(report)
    candidates = [profile for profile in profiles if profile.get("ftse100") is True and profile.get("ticker")]
    profiles_by_ticker = {profile["ticker"]: profile for profile in candidates}
    failures = []

    def fetch_profile(profile):
        ticker = profile["ticker"]
        try:
            return ticker, extract_dividend_series(client.fetch_dividends(ticker)), None
        except RuntimeError as error:
            return ticker, None, {"ticker": ticker, "reason": str(error), "scope": "dividend history"}

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = [executor.submit(fetch_profile, profile) for profile in candidates]
        for completed, future in enumerate(as_completed(futures), 1):
            ticker, metric, failure = future.result()
            if failure:
                failures.append(failure)
            elif not metric and profiles_by_ticker[ticker].get("paysDividend") is not False:
                failures.append({"ticker": ticker, "reason": "no dividend history", "scope": "dividend history"})
            else:
                company_reports = sorted(by_ticker.get(ticker, []), key=lambda item: item.get("reportDate", ""))
                if company_reports:
                    company_reports[-1].setdefault("metrics", {})["dividendPerShare"] = metric
                    dividends_by_year = {int(period["endDate"][:4]): period["value"] for period in metric["periods"]}
                    for report in company_reports:
                        year = int(report["reportDate"][:4])
                        if year in dividends_by_year:
                            report.setdefault("summary", {})["dividendPerShare"] = dividends_by_year[year]
            if completed % 10 == 0 or completed == len(candidates):
                print(f"Processed dividend history {completed}/{len(candidates)}", flush=True)
    failures.sort(key=lambda item: item["ticker"])
    return reports, failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company-database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--failures-output", type=Path)
    parser.add_argument("--delay", type=float, default=0.35)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--dividends-only", action="store_true")
    args = parser.parse_args()
    profiles = json.loads(args.company_database.read_text())
    client = YahooClient(delay=args.delay)
    if args.dividends_only:
        reports = json.loads(args.output.read_text())
        reports, failures = enrich_existing_dividends(profiles, reports, client, workers=args.workers)
    else:
        reports, failures = run(profiles, client, workers=args.workers)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n")
    if args.failures_output:
        args.failures_output.parent.mkdir(parents=True, exist_ok=True)
        args.failures_output.write_text(json.dumps(failures, ensure_ascii=False, indent=2) + "\n")
    print(f"Archived {len(reports)} annual reports; failures: {len(failures)}")


if __name__ == "__main__":
    main()
