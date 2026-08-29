#!/usr/bin/env python3
"""Build upcoming dividend events using official-first source precedence.

Source order:
1. Company Investor Relations (official corporate pages)
2. SEC/EDGAR filings
3. Alpha Vantage declared dividend events
4. A clearly-labelled estimate derived from historical Alpha Vantage events

The script patches ``dividendEvents`` into the app snapshot. It never lets a
lower-priority source overwrite a higher-priority confirmed event.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable

try:
    from .alpha_vantage_dividends import fetch_dividends
except ImportError:
    from alpha_vantage_dividends import fetch_dividends


DEFAULT_USER_AGENT = "DividendIntelligence/1.0 dividend-events"
ECB_DAILY_RATES_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}
DATE_TOKEN = (
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},\s+20\d{2}"
)
ROLE_PATTERNS = {
    "paymentDate": re.compile(
        rf"(?:payable|payment(?:\s+date)?(?:\s+is)?|to be paid|will be paid)\s+(?:on\s+)?({DATE_TOKEN})",
        re.IGNORECASE,
    ),
    "recordDate": re.compile(
        rf"(?:record\s+date(?:\s+is)?|shareholders?\s+of\s+record(?:\s+as\s+of)?(?:\s+the\s+close\s+of\s+business)?(?:\s+on)?)"
        rf"\s*[:,-]?\s*({DATE_TOKEN})",
        re.IGNORECASE,
    ),
    "exDividendDate": re.compile(
        rf"(?:ex[-\s]?dividend\s+date(?:\s+is)?|ex[-\s]?date(?:\s+is)?)\s*[:,-]?\s*({DATE_TOKEN})",
        re.IGNORECASE,
    ),
    "declarationDate": re.compile(
        rf"(?:declared|declaration\s+date(?:\s+is)?)\s+(?:on\s+)?({DATE_TOKEN})",
        re.IGNORECASE,
    ),
}
AMOUNT_PATTERNS = [
    re.compile(r"(?:cash\s+)?dividend(?:\s+of)?[^$€£]{0,90}([$€£])\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
    re.compile(r"([$€£])\s*([0-9]+(?:\.[0-9]+)?)\s+per\s+(?:common\s+)?share", re.IGNORECASE),
]


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        self._href = dict(attrs).get("href")
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            self.links.append((self._href, " ".join(self._text).strip()))
        if tag.lower() == "a":
            self._href = None
            self._text = []


def parse_human_date(value: str) -> date | None:
    match = re.fullmatch(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(\d{1,2}),\s+(20\d{2})",
        value.strip(),
        re.IGNORECASE,
    )
    if not match:
        return None
    try:
        return date(int(match.group(3)), MONTHS[match.group(1).lower()], int(match.group(2)))
    except ValueError:
        return None


def iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def parse_ecb_rates(document: str) -> dict[str, Any]:
    """Parse the ECB daily reference feed (currencies quoted per EUR)."""
    root = ET.fromstring(document)
    dated = next((node for node in root.iter() if node.attrib.get("time")), None)
    if dated is None:
        raise ValueError("ECB response does not contain a dated rate table")
    rates = {"EUR": 1.0}
    for node in dated:
        currency = node.attrib.get("currency")
        raw_rate = node.attrib.get("rate")
        if currency and raw_rate:
            rates[currency.upper()] = float(raw_rate)
    if len(rates) < 2:
        raise ValueError("ECB response does not contain exchange rates")
    return {
        "base": "EUR",
        "asOf": dated.attrib["time"],
        "source": "Banco Central Europeo",
        "sourceURL": ECB_DAILY_RATES_URL,
        "rates": rates,
    }


def fetch_ecb_rates() -> dict[str, Any]:
    request = urllib.request.Request(ECB_DAILY_RATES_URL, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        return parse_ecb_rates(response.read().decode("utf-8"))


def strip_html(document: str) -> str:
    document = re.sub(r"(?is)<script.*?>.*?</script>", " ", document)
    document = re.sub(r"(?is)<style.*?>.*?</style>", " ", document)
    document = re.sub(r"(?s)<[^>]+>", " ", document)
    return re.sub(r"\s+", " ", unescape(document)).strip()


def fetch_text(url: str, user_agent: str = DEFAULT_USER_AGENT, timeout: int = 20) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def currency_from_symbol(symbol: str | None, fallback: str | None) -> str:
    if fallback:
        return fallback.upper()
    return {"€": "EUR", "£": "GBP", "$": "USD"}.get(symbol or "", "USD")


def find_amount(text: str, center: int | None = None) -> tuple[float | None, str | None]:
    if center is not None:
        windows = [text[max(0, center - 1000): center + 1000], text]
    else:
        windows = [text]
    for window in windows:
        for pattern in AMOUNT_PATTERNS:
            match = pattern.search(window)
            if match:
                try:
                    amount = float(match.group(2))
                except ValueError:
                    continue
                if 0 < amount < 1000:
                    return amount, match.group(1)
    return None, None


def extract_event_from_text(
    text: str,
    *,
    ticker: str,
    company: str,
    currency: str | None,
    source: str,
    source_url: str,
    source_priority: int,
    confidence: int,
    today: date,
    horizon_days: int,
) -> dict[str, Any] | None:
    """Conservatively extract one upcoming declared dividend from a page."""
    normalized = re.sub(r"\s+", " ", unescape(text)).strip()
    if "dividend" not in normalized.lower() and "distribution" not in normalized.lower():
        return None

    role_matches: dict[str, list[tuple[date, int]]] = defaultdict(list)
    for role, pattern in ROLE_PATTERNS.items():
        for match in pattern.finditer(normalized):
            parsed = parse_human_date(match.group(1))
            if parsed:
                role_matches[role].append((parsed, match.start()))

    future_candidates: list[tuple[date, int, str]] = []
    for role in ("paymentDate", "exDividendDate", "recordDate"):
        for parsed, position in role_matches.get(role, []):
            if today <= parsed <= today + timedelta(days=horizon_days):
                future_candidates.append((parsed, position, role))
    if not future_candidates:
        return None

    future_candidates.sort(key=lambda item: (item[0], {"paymentDate": 0, "exDividendDate": 1, "recordDate": 2}[item[2]]))
    _, center, _ = future_candidates[0]
    amount, symbol = find_amount(normalized, center)
    if amount is None:
        return None

    dates: dict[str, str | None] = {}
    for role in ROLE_PATTERNS:
        candidates = [item for item in role_matches.get(role, []) if abs(item[1] - center) <= 1800]
        if not candidates:
            dates[role] = None
            continue
        selected = min(candidates, key=lambda item: abs(item[1] - center))[0]
        dates[role] = selected.isoformat()

    return {
        "ticker": ticker,
        "company": company,
        "amount": round(amount, 6),
        "currency": currency_from_symbol(symbol, currency),
        **dates,
        "status": "confirmed",
        "source": source,
        "sourceURL": source_url,
        "sourcePriority": source_priority,
        "confidence": confidence,
        "estimatedReason": None,
    }


def candidate_links(base_url: str, html_document: str, limit: int = 6) -> list[str]:
    parser = LinkParser()
    try:
        parser.feed(html_document)
    except Exception:
        return []
    scored: list[tuple[int, str]] = []
    seen: set[str] = set()
    base_host = urllib.parse.urlparse(base_url).netloc.lower()
    for href, label in parser.links:
        absolute = urllib.parse.urljoin(base_url, href)
        parsed = urllib.parse.urlparse(absolute)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != base_host:
            continue
        key = (label + " " + absolute).lower()
        score = 0
        if "dividend" in key or "distribution" in key:
            score += 12
        if "press-release" in key or "press_release" in key or "news-release" in key:
            score += 6
        if "/news" in key or "newsroom" in key:
            score += 3
        if "2026" in key:
            score += 2
        if score and absolute not in seen:
            scored.append((score, absolute))
            seen.add(absolute)
    scored.sort(key=lambda item: item[0], reverse=True)
    return [url for _, url in scored[:limit]]


def find_ir_event(
    profile: dict[str, Any],
    configured_urls: list[str],
    *,
    today: date,
    horizon_days: int,
) -> dict[str, Any] | None:
    ticker = (profile.get("ticker") or "").upper()
    company = profile.get("name") or ticker
    roots = [url for url in configured_urls if url]
    if profile.get("investorRelationsURL"):
        roots.append(profile["investorRelationsURL"])
    seen: set[str] = set()
    for root in roots:
        if root in seen:
            continue
        seen.add(root)
        try:
            document = fetch_text(root)
        except Exception:
            continue
        event = extract_event_from_text(
            strip_html(document), ticker=ticker, company=company, currency=profile.get("currency"),
            source="Investor Relations", source_url=root, source_priority=1, confidence=100,
            today=today, horizon_days=horizon_days,
        )
        if event:
            return event
        for url in candidate_links(root, document):
            if url in seen:
                continue
            seen.add(url)
            try:
                child = fetch_text(url)
            except Exception:
                continue
            event = extract_event_from_text(
                strip_html(child), ticker=ticker, company=company, currency=profile.get("currency"),
                source="Investor Relations", source_url=url, source_priority=1, confidence=100,
                today=today, horizon_days=horizon_days,
            )
            if event:
                return event
    return None


def find_sec_event(
    profile: dict[str, Any],
    reports: list[dict[str, Any]],
    *,
    today: date,
    horizon_days: int,
    sec_user_agent: str,
) -> dict[str, Any] | None:
    ticker = (profile.get("ticker") or "").upper()
    company = profile.get("name") or ticker
    latest = sorted(reports, key=lambda item: item.get("filingDate", ""), reverse=True)[:2]
    urls = [item.get("secURL") for item in latest if item.get("secURL")]
    for url in urls:
        try:
            document = fetch_text(url, user_agent=sec_user_agent)
        except Exception:
            continue
        event = extract_event_from_text(
            strip_html(document), ticker=ticker, company=company, currency=profile.get("currency"),
            source="SEC/EDGAR", source_url=url, source_priority=2, confidence=98,
            today=today, horizon_days=horizon_days,
        )
        if event:
            return event
    return None


def alpha_future_events(
    ticker: str,
    company: str,
    currency: str | None,
    payload: dict[str, Any],
    *,
    today: date,
    horizon_days: int,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    horizon = today + timedelta(days=horizon_days)
    for row in payload.get("data", []):
        amount = row.get("amount")
        try:
            amount_value = float(amount)
        except (TypeError, ValueError):
            continue
        dates = {
            "declarationDate": row.get("declaration_date") or None,
            "exDividendDate": row.get("ex_dividend_date") or None,
            "recordDate": row.get("record_date") or None,
            "paymentDate": row.get("payment_date") or None,
        }
        relevant: list[date] = []
        for value in (dates["paymentDate"], dates["exDividendDate"], dates["recordDate"]):
            if not value:
                continue
            try:
                relevant.append(date.fromisoformat(value))
            except ValueError:
                pass
        if not relevant or max(relevant) < today or min(relevant) > horizon:
            continue
        result.append({
            "ticker": ticker,
            "company": company,
            "amount": round(amount_value, 6),
            "currency": (currency or "USD").upper(),
            **dates,
            "status": "confirmed",
            "source": "Alpha Vantage",
            "sourceURL": "https://www.alphavantage.co/",
            "sourcePriority": 3,
            "confidence": 90,
            "estimatedReason": None,
        })
    return sorted(result, key=event_sort_key)


def event_history(payload: dict[str, Any]) -> list[tuple[date, dict[str, Any]]]:
    result: list[tuple[date, dict[str, Any]]] = []
    for row in payload.get("data", []):
        raw = row.get("payment_date") or row.get("ex_dividend_date")
        if not raw:
            continue
        try:
            when = date.fromisoformat(raw)
            amount = float(row.get("amount"))
        except (ValueError, TypeError):
            continue
        if amount > 0:
            result.append((when, row))
    return sorted(result, key=lambda item: item[0])


def estimate_from_alpha_history(
    ticker: str,
    company: str,
    currency: str | None,
    payload: dict[str, Any],
    *,
    today: date,
    horizon_days: int,
) -> dict[str, Any] | None:
    history = [(when, row) for when, row in event_history(payload) if when < today]
    if len(history) < 4:
        return None
    recent = history[-9:]
    intervals = [(right[0] - left[0]).days for left, right in zip(recent, recent[1:])]
    intervals = [value for value in intervals if 15 <= value <= 450]
    if len(intervals) < 3:
        return None
    interval = int(round(statistics.median(intervals)))
    predicted_payment = history[-1][0] + timedelta(days=interval)
    while predicted_payment < today:
        predicted_payment += timedelta(days=interval)
    if predicted_payment > today + timedelta(days=horizon_days):
        return None

    last_amount = float(history[-1][1]["amount"])
    change_events: list[tuple[int, float]] = []
    raise_history = history[-16:]
    for (previous_date, previous), (current_date, current) in zip(raise_history, raise_history[1:]):
        try:
            old = float(previous["amount"])
            new = float(current["amount"])
        except (TypeError, ValueError):
            continue
        if old > 0 and new > old * 1.001:
            growth = new / old - 1
            if 0 < growth <= 0.25:
                change_events.append((current_date.month, growth))

    estimated_amount = last_amount
    reason = f"Patrón histórico de pago cada ~{interval} días; importe mantiene el último dividendo."
    if len(change_events) >= 2:
        month_counts = Counter(month for month, _ in change_events)
        raise_month, occurrences = month_counts.most_common(1)[0]
        month_distance = min((predicted_payment.month - raise_month) % 12, (raise_month - predicted_payment.month) % 12)
        growth_rates = [growth for month, growth in change_events if month == raise_month]
        if occurrences >= 2 and month_distance <= 1 and growth_rates:
            growth = statistics.median(growth_rates)
            estimated_amount = last_amount * (1 + growth)
            reason = (
                f"Patrón histórico de pago cada ~{interval} días y subida anual habitual "
                f"de ~{growth * 100:.1f}% en este periodo."
            )

    def median_offset(field: str) -> int | None:
        offsets: list[int] = []
        for payment, row in history[-8:]:
            raw = row.get(field)
            if not raw:
                continue
            try:
                other = date.fromisoformat(raw)
            except ValueError:
                continue
            delta = (payment - other).days
            if -10 <= delta <= 120:
                offsets.append(delta)
        return int(round(statistics.median(offsets))) if offsets else None

    ex_offset = median_offset("ex_dividend_date")
    record_offset = median_offset("record_date")
    declaration_offset = median_offset("declaration_date")
    variability = statistics.pstdev(intervals) if len(intervals) > 1 else 0
    confidence = 82 if variability <= 8 else 72 if variability <= 20 else 62

    return {
        "ticker": ticker,
        "company": company,
        "amount": round(estimated_amount, 6),
        "currency": (currency or "USD").upper(),
        "declarationDate": iso(predicted_payment - timedelta(days=declaration_offset)) if declaration_offset is not None else None,
        "exDividendDate": iso(predicted_payment - timedelta(days=ex_offset)) if ex_offset is not None else None,
        "recordDate": iso(predicted_payment - timedelta(days=record_offset)) if record_offset is not None else None,
        "paymentDate": predicted_payment.isoformat(),
        "status": "estimated",
        "source": "Estimación",
        "sourceURL": None,
        "sourcePriority": 4,
        "confidence": confidence,
        "estimatedReason": reason,
    }


def event_next_date(event: dict[str, Any]) -> date:
    values = []
    for key in ("exDividendDate", "recordDate", "paymentDate", "declarationDate"):
        raw = event.get(key)
        if not raw:
            continue
        try:
            values.append(date.fromisoformat(raw))
        except ValueError:
            pass
    return min(values) if values else date.max


def event_sort_key(event: dict[str, Any]) -> tuple[date, int, str]:
    return event_next_date(event), int(event.get("sourcePriority", 99)), event.get("ticker", "")


def load_ir_sources(path: Path | None) -> dict[str, list[str]]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text())
    result: dict[str, list[str]] = {}
    for row in payload:
        ticker = (row.get("ticker") or "").upper()
        urls = [url for url in row.get("urls", []) if isinstance(url, str) and url.startswith("http")]
        if ticker and urls:
            result[ticker] = urls
    return result


def ranked_candidates(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = {
        (row.get("ticker") or "").upper(): row
        for row in snapshot.get("companyProfiles", [])
        if row.get("ticker")
    }
    consensus = {
        (row.get("ticker") or "").upper(): row
        for row in snapshot.get("consensus", [])
        if row.get("ticker")
    }
    held = {(row.get("ticker") or "").upper() for row in snapshot.get("holdings", []) if row.get("ticker")}
    candidates = []
    for ticker, profile in profiles.items():
        signal = consensus.get(ticker, {})
        dividend_yield = signal.get("yield")
        if dividend_yield is None:
            raw = profile.get("dividendYield")
            dividend_yield = raw * 100 if isinstance(raw, (int, float)) and 0 <= raw <= 0.25 else raw
        pays = profile.get("paysDividend") is True or (isinstance(dividend_yield, (int, float)) and dividend_yield > 0)
        if not pays:
            continue
        rank = signal.get("opportunityRank") or 9999
        candidates.append((
            0 if ticker in held else 1,
            rank,
            -(signal.get("holders") or 0),
            -(dividend_yield or 0),
            ticker,
            profile,
        ))
    candidates.sort(key=lambda item: item[:-1])
    return [item[-1] for item in candidates]


def build_events(
    snapshot: dict[str, Any],
    *,
    ir_sources: dict[str, list[str]],
    today: date,
    horizon_days: int,
    max_ir: int,
    max_sec: int,
    max_alpha: int,
    alpha_key: str | None,
    sec_user_agent: str,
) -> list[dict[str, Any]]:
    candidates = ranked_candidates(snapshot)
    reports_by_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for report in snapshot.get("companyReports", []):
        ticker = (report.get("ticker") or "").upper()
        if ticker:
            reports_by_ticker[ticker].append(report)

    resolved: set[str] = set()
    events: list[dict[str, Any]] = []

    for profile in candidates[:max_ir]:
        ticker = profile["ticker"].upper()
        event = find_ir_event(
            profile, ir_sources.get(ticker, []), today=today, horizon_days=horizon_days,
        )
        if event:
            events.append(event)
            resolved.add(ticker)

    sec_checked = 0
    for profile in candidates:
        ticker = profile["ticker"].upper()
        if ticker in resolved or sec_checked >= max_sec:
            continue
        reports = reports_by_ticker.get(ticker, [])
        if not reports:
            continue
        sec_checked += 1
        event = find_sec_event(
            profile, reports, today=today, horizon_days=horizon_days, sec_user_agent=sec_user_agent,
        )
        if event:
            events.append(event)
            resolved.add(ticker)

    if alpha_key:
        alpha_checked = 0
        for profile in candidates:
            ticker = profile["ticker"].upper()
            if ticker in resolved or alpha_checked >= max_alpha:
                continue
            alpha_checked += 1
            try:
                payload = fetch_dividends(ticker, alpha_key)
            except Exception as exc:
                message = str(exc).lower()
                if "25 requests per day" in message or "rate limit" in message or "premium" in message:
                    break
                continue
            declared = alpha_future_events(
                ticker, profile.get("name") or ticker, profile.get("currency"), payload,
                today=today, horizon_days=horizon_days,
            )
            if declared:
                events.extend(declared)
                resolved.add(ticker)
                continue
            estimate = estimate_from_alpha_history(
                ticker, profile.get("name") or ticker, profile.get("currency"), payload,
                today=today, horizon_days=horizon_days,
            )
            if estimate:
                events.append(estimate)
                resolved.add(ticker)

    # Keep only upcoming events and de-duplicate within each ticker/date.
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events:
        next_date = event_next_date(event)
        if next_date < today or next_date > today + timedelta(days=horizon_days):
            continue
        key = (event["ticker"], next_date.isoformat())
        current = unique.get(key)
        if current is None or event.get("sourcePriority", 99) < current.get("sourcePriority", 99):
            unique[key] = event
    return sorted(unique.values(), key=event_sort_key)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--ir-sources", type=Path)
    parser.add_argument("--horizon-days", type=int, default=180)
    parser.add_argument("--max-ir", type=int, default=30)
    parser.add_argument("--max-sec", type=int, default=30)
    parser.add_argument("--max-alpha", type=int, default=20)
    parser.add_argument("--today", help="Override YYYY-MM-DD for deterministic tests/manual runs")
    args = parser.parse_args()

    today = date.fromisoformat(args.today) if args.today else date.today()
    snapshot = json.loads(args.snapshot.read_text())
    try:
        snapshot["exchangeRates"] = fetch_ecb_rates()
    except Exception as exc:
        # A transient FX outage must not discard the last known auditable table.
        if not snapshot.get("exchangeRates"):
            raise RuntimeError("No ECB exchange rates available for EUR dividend conversion") from exc
    events = build_events(
        snapshot,
        ir_sources=load_ir_sources(args.ir_sources),
        today=today,
        horizon_days=max(1, args.horizon_days),
        max_ir=max(0, args.max_ir),
        max_sec=max(0, args.max_sec),
        max_alpha=max(0, min(args.max_alpha, 20)),
        alpha_key=os.environ.get("ALPHA_VANTAGE_API_KEY"),
        sec_user_agent=os.environ.get("SEC_USER_AGENT", DEFAULT_USER_AGENT),
    )
    snapshot["dividendEvents"] = events
    snapshot["generatedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    args.snapshot.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps({
        "dividendEvents": len(events),
        "confirmed": sum(item["status"] == "confirmed" for item in events),
        "estimated": sum(item["status"] == "estimated" for item in events),
        "sources": dict(Counter(item["source"] for item in events)),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
