#!/usr/bin/env python3
"""Publish observed quarterly EPS for issuers that paid XTB dividends recently."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIVIDENDS = ROOT / "data/public/xtb-dividends.json"
OUTPUT = ROOT / "data/public/xtb-eps.json"
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
SEC_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
AV_QUERY = "https://www.alphavantage.co/query"
SEC_AGENT = os.getenv("SEC_USER_AGENT") or "DividendDashboard/1.0 research"
AV_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")
AV_DAILY_BUDGET = int(os.getenv("XTB_EPS_AV_BUDGET", "12"))

US_OVERRIDES = {"BAM1": "BAM"}
AV_OVERRIDES = {
    "BAM1.US": "BAM",
    "ABF.UK": "ABF.LON", "BATS.UK": "BATS.LON",
    "BNZL.UK": "BNZL.LON", "DGE.UK": "DGE.LON",
    "LSEG.UK": "LSEG.LON", "SVT.UK": "SVT.LON",
    "ENG.ES": "ENG.MAD", "IBE1.ES": "IBE.MAD", "LOG.ES": "LOG.MAD",
    "NTGY.ES": "NTGY.MAD", "RED.ES": "RED.MAD", "REP1.ES": "REP.MAD",
    "SAN1.ES": "SAN.MAD", "VIS.ES": "VIS.MAD",
    "KER.FR": "KER.PAR", "MC.FR": "MC.PAR", "VRLA.FR": "VRLA.PAR",
    "MBG.DE": "MBG.DEX", "2PP.DE": "2PP.DEX",
    "NOVOB.DK": "NOVO-B.CPH", "WKL.NL": "WKL.AMS",
}


def request_json(url: str, agent: str = SEC_AGENT) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": agent, "Accept": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                return json.load(response)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("Unreachable")


def year_before(day: date) -> date:
    try:
        return day.replace(year=day.year - 1)
    except ValueError:
        return day.replace(year=day.year - 1, day=28)


def eligible_receipts(payload: dict, today: date) -> list[dict]:
    cutoff = year_before(today).isoformat()
    return [r for r in payload.get("receipts", []) if r.get("type") == "Acción" and cutoff <= r.get("date", "") <= today.isoformat()]


def active_companies(receipts: list[dict]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for item in receipts:
        ticker = item["ticker"]
        entry = result.setdefault(ticker, {
            "ticker": ticker, "company": item["company"],
            "lastDividendDate": item["date"], "cashLast12MonthsEUR": 0.0,
        })
        entry["lastDividendDate"] = max(entry["lastDividendDate"], item["date"])
        entry["cashLast12MonthsEUR"] += float(item["amountEUR"])
    for entry in result.values():
        entry["cashLast12MonthsEUR"] = round(entry["cashLast12MonthsEUR"], 2)
    return result


def sec_ciks() -> dict[str, int]:
    rows = request_json(SEC_TICKERS).values()
    return {str(row["ticker"]).upper(): int(row["cik_str"]) for row in rows}


def quarterly_sec_periods(facts: dict, cik: int, today: date) -> list[dict]:
    namespaces = [
        ("us-gaap", "EarningsPerShareDiluted", "BPA diluido GAAP"),
        ("ifrs-full", "DilutedEarningsLossPerShare", "BPA diluido IFRS"),
        ("us-gaap", "EarningsPerShareBasic", "BPA básico GAAP"),
        ("ifrs-full", "BasicEarningsLossPerShare", "BPA básico IFRS"),
    ]
    for namespace, concept, metric in namespaces:
        field = facts.get("facts", {}).get(namespace, {}).get(concept, {})
        units = field.get("units", {})
        candidates = []
        for unit, values in units.items():
            if not unit.endswith("/shares"):
                continue
            for item in values:
                if not item.get("start") or not item.get("end") or not item.get("filed"):
                    continue
                if item.get("form") not in ("10-Q", "10-K", "20-F", "6-K"):
                    continue
                try:
                    start, end = date.fromisoformat(item["start"]), date.fromisoformat(item["end"])
                    filing = date.fromisoformat(item["filed"])
                    eps = float(item["val"])
                except (ValueError, TypeError, KeyError):
                    continue
                if not (70 <= (end - start).days <= 110 and end <= today and filing <= today):
                    continue
                if end < today - timedelta(days=1600):
                    continue
                accn = item.get("accn", "")
                source = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/" if accn else SEC_FACTS.format(cik=cik)
                candidates.append({
                    "periodStart": item["start"], "periodEnd": item["end"],
                    "eps": eps, "unit": unit, "reportedAt": item["filed"],
                    "form": item["form"], "sourceURL": source, "metric": metric,
                })
        if candidates:
            # A later filing may restate a comparative quarter. Keep the newest filed value
            # for each period, but never combine basic and diluted EPS in one series.
            latest: dict[str, dict] = {}
            for candidate in candidates:
                end = candidate["periodEnd"]
                if end not in latest or candidate["reportedAt"] > latest[end]["reportedAt"]:
                    latest[end] = candidate
            return sorted(latest.values(), key=lambda x: x["periodEnd"], reverse=True)[:12]
    return []


def fetch_sec(ticker: str, ciks: dict[str, int], today: date) -> tuple[list[dict], str | None]:
    if not ticker.endswith(".US"):
        return [], None
    symbol = US_OVERRIDES.get(ticker.split(".")[0], ticker.split(".")[0])
    cik = ciks.get(symbol)
    if not cik:
        return [], "CIK no encontrado"
    try:
        facts = request_json(SEC_FACTS.format(cik=cik))
        return quarterly_sec_periods(facts, cik, today), None
    except Exception as exc:
        return [], f"SEC temporalmente no disponible ({type(exc).__name__})"


def av_symbol(ticker: str) -> str:
    if ticker in AV_OVERRIDES:
        return AV_OVERRIDES[ticker]
    if ticker.endswith(".US"):
        return ticker[:-3]
    return ""


def fetch_av(ticker: str, today: date) -> tuple[list[dict], str | None]:
    symbol = av_symbol(ticker)
    if not symbol:
        return [], "Ticker sin correspondencia verificada"
    url = AV_QUERY + "?" + urllib.parse.urlencode({"function": "EARNINGS", "symbol": symbol, "apikey": AV_KEY})
    try:
        payload = request_json(url, agent="DividendDashboard/1.0")
    except Exception as exc:
        return [], f"Alpha Vantage temporalmente no disponible ({type(exc).__name__})"
    if payload.get("Information") or payload.get("Note"):
        return [], "Límite de consultas de Alpha Vantage"
    if payload.get("Error Message"):
        return [], "Símbolo sin datos de BPA en Alpha Vantage"
    candidates = []
    for row in payload.get("quarterlyEarnings", []):
        try:
            end = date.fromisoformat(row["fiscalDateEnding"])
            eps = float(row["reportedEPS"])
        except (ValueError, TypeError, KeyError):
            continue
        if end > today:
            continue
        reported = row.get("reportedDate")
        if reported:
            try:
                if date.fromisoformat(reported) > today:
                    continue
            except ValueError:
                reported = None
        candidates.append({
            "periodStart": None, "periodEnd": end.isoformat(), "eps": eps,
            "unit": payload.get("currency") or None,
            "reportedAt": reported, "form": "Earnings",
            "sourceURL": "https://www.alphavantage.co/documentation/#earnings",
        })
    unique = {p["periodEnd"]: p for p in candidates}
    periods = sorted(unique.values(), key=lambda x: x["periodEnd"], reverse=True)[:12]
    if len(periods) < 2:
        return [], "Sin serie trimestral utilizable en Alpha Vantage"
    return periods, None


def quarter_gap(a: str, b: str) -> bool:
    days = (date.fromisoformat(a) - date.fromisoformat(b)).days
    return 70 <= days <= 120


def yoy_comparator(latest: dict, periods: list[dict]) -> dict | None:
    end = date.fromisoformat(latest["periodEnd"])
    eligible = []
    for candidate in periods:
        days = (end - date.fromisoformat(candidate["periodEnd"])).days
        if 335 <= days <= 395:
            eligible.append((abs(days - 365), candidate))
    return min(eligible, key=lambda x: x[0])[1] if eligible else None


def streak(periods: list[dict], mode: str) -> dict:
    if not periods:
        return {"count": 0, "comparisons": 0, "latest": None}
    count = 0
    comparisons = 0
    for index, current in enumerate(periods):
        if mode == "qoq":
            older = periods[index + 1] if index + 1 < len(periods) and quarter_gap(current["periodEnd"], periods[index + 1]["periodEnd"]) else None
        else:
            older = yoy_comparator(current, periods)
        if not older:
            break
        comparisons += 1
        if current["eps"] <= older["eps"]:
            break
        count += 1
        if index + 1 < len(periods) and not quarter_gap(current["periodEnd"], periods[index + 1]["periodEnd"]):
            break
    return {"count": count, "comparisons": comparisons, "latest": periods[0]["periodEnd"]}


def main() -> None:
    today = date.today()
    dividends = json.loads(DIVIDENDS.read_text(encoding="utf-8"))
    active = active_companies(eligible_receipts(dividends, today))
    old = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {}
    cache = old.get("alphaCache", {})
    try:
        ciks = sec_ciks()
    except Exception:
        ciks = {}
    sec_results: dict[str, tuple[list[dict], str | None]] = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_by_ticker = {
            executor.submit(fetch_sec, ticker, ciks, today): ticker
            for ticker in active
        }
        for future in as_completed(future_by_ticker):
            sec_results[future_by_ticker[future]] = future.result()

    candidates = sorted((ticker for ticker in active if ticker.endswith(".US")), key=lambda ticker: (
        bool(sec_results[ticker][0]), -active[ticker]["cashLast12MonthsEUR"]
    ))
    attempted = 0
    if AV_KEY:
        for ticker in candidates:
            item = cache.get(ticker, {})
            last = item.get("checkedAt")
            if last and (today - date.fromisoformat(last)).days < 20:
                continue
            if attempted >= AV_DAILY_BUDGET:
                break
            attempted += 1
            periods, error = fetch_av(ticker, today)
            if error == "Límite de consultas de Alpha Vantage":
                break
            cache[ticker] = {"checkedAt": today.isoformat(), "periods": periods, "error": error, "symbol": av_symbol(ticker)}
            time.sleep(1.2)

    companies = []
    for ticker, company in sorted(active.items()):
        sec_periods, sec_error = sec_results[ticker]
        prior = next((row for row in old.get("companies", []) if row["ticker"] == ticker), None)
        if not sec_periods and sec_error and prior and prior.get("source") == "SEC EDGAR":
            sec_periods = prior.get("periods", [])
        av_periods = cache.get(ticker, {}).get("periods", [])
        # Keep a homogeneous EPS definition. A complete provider series is
        # preferable to mixing GAAP and potentially adjusted reported EPS.
        use_av = len(av_periods) >= 8 and (len(sec_periods) < 12 or len(av_periods) >= len(sec_periods))
        periods = av_periods if use_av else sec_periods
        provider = "Alpha Vantage" if use_av else "SEC EDGAR" if sec_periods else None
        company.update({
            "source": provider, "metric": "BPA comunicado" if use_av else
            (sec_periods[0].get("metric") if sec_periods else None),
            "periods": periods,
            "availableReports": len(periods),
            "complete12": len(periods) == 12 and all(
                quarter_gap(periods[i]["periodEnd"], periods[i + 1]["periodEnd"])
                for i in range(11)
            ),
            "streakYoY": streak(periods, "yoy"),
            "streakQoQ": streak(periods, "qoq"),
            "status": "available" if periods else
            ("Emisor fuera de la cobertura trimestral SEC" if not ticker.endswith(".US") else
             cache.get(ticker, {}).get("error") or sec_error or "Sin BPA trimestral comparable"),
        })
        companies.append(company)
    output = {
        "asOf": today.isoformat(),
        "dividendSourceAsOf": dividends.get("asOf"),
        "windowStart": year_before(today).isoformat(),
        "method": "Trimestres individuales; comparación interanual con el mismo trimestre 335–395 días antes. La racha se interrumpe ante ausencia de un trimestre, dato faltante o BPA no creciente.",
        "companies": companies,
        "alphaCache": {ticker: cache[ticker] for ticker in active if ticker in cache},
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "companies": len(companies), "withEPS": sum(bool(x["periods"]) for x in companies),
        "complete12": sum(x["complete12"] for x in companies),
        "alphaRequests": attempted,
    }))


if __name__ == "__main__":
    main()
