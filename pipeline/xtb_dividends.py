#!/usr/bin/env python3
"""Normalize real XTB dividend cash receipts for Dividend Intelligence."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

GOALS = (1000, 2000, 5000, 10000)


def parse_date(value: Any) -> date:
    text = str(value).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()


def normalize_rows(values: list[list[Any]]) -> list[dict[str, Any]]:
    if not values:
        return []
    headers = [str(v).strip() for v in values[0]]
    idx = {name: i for i, name in enumerate(headers)}
    required = {"Fecha", "Empresa", "Ticker", "Tipo", "Importe", "Moneda base", "ID aviso"}
    missing = required - set(idx)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    def cell(row: list[Any], name: str, default: Any = "") -> Any:
        pos = idx.get(name)
        return row[pos] if pos is not None and pos < len(row) else default

    unique: dict[str, dict[str, Any]] = {}
    for row in values[1:]:
        if not row:
            continue
        if str(cell(row, "Moneda base")).upper() != "EUR":
            raise ValueError("Dividendos must be normalized to EUR")
        notice_id = str(cell(row, "ID aviso")).strip()
        if not notice_id:
            raise ValueError("Dividend row without notice ID")
        item = {
            "date": parse_date(cell(row, "Fecha")).isoformat(),
            "company": str(cell(row, "Empresa")).strip(),
            "ticker": str(cell(row, "Ticker")).strip().upper(),
            "market": str(cell(row, "Mercado")).strip(),
            "type": str(cell(row, "Tipo")).strip() or "Desconocido",
            "amountEUR": round(float(cell(row, "Importe")), 2),
            "noticeURL": str(cell(row, "Enlace al aviso")).strip() or None,
            "noticeID": notice_id,
        }
        if notice_id in unique and unique[notice_id] != item:
            raise ValueError(f"Conflicting duplicate notice ID: {notice_id}")
        unique[notice_id] = item
    return sorted(unique.values(), key=lambda x: (x["date"], x["noticeID"]), reverse=True)


def build_payload(receipts: list[dict[str, Any]]) -> dict[str, Any]:
    today = date.today()
    as_of = max((date.fromisoformat(r["date"]) for r in receipts), default=today)
    last12_start = date(as_of.year - 1, as_of.month, as_of.day) + timedelta(days=1)
    historical = round(sum(r["amountEUR"] for r in receipts), 2)
    current_year = round(sum(r["amountEUR"] for r in receipts if date.fromisoformat(r["date"]).year == as_of.year), 2)
    last12 = round(sum(r["amountEUR"] for r in receipts if last12_start <= date.fromisoformat(r["date"]) <= as_of), 2)

    monthly: dict[str, float] = defaultdict(float)
    ticker_totals: dict[str, float] = defaultdict(float)
    ticker_names: dict[str, str] = {}
    ticker_types: dict[str, str] = {}
    type_totals: dict[str, float] = defaultdict(float)
    for r in receipts:
        monthly[r["date"][:7]] += r["amountEUR"]
        ticker_totals[r["ticker"]] += r["amountEUR"]
        ticker_names[r["ticker"]] = r["company"]
        ticker_types[r["ticker"]] = r["type"]
        type_totals[r["type"]] += r["amountEUR"]

    ranking_pairs = sorted(ticker_totals.items(), key=lambda x: x[1], reverse=True)
    ranking = [{
        "ticker": ticker,
        "company": ticker_names[ticker],
        "type": ticker_types[ticker],
        "amountEUR": round(amount, 2),
        "sharePct": round(amount / historical * 100, 2) if historical else 0,
    } for ticker, amount in ranking_pairs]

    return {
        "asOf": as_of.isoformat(),
        "currency": "EUR",
        "source": {"kind": "google_sheets", "tab": "Dividendos", "authority": "XTB cash receipts imported from Gmail"},
        "summary": {
            "historicalTotalEUR": historical,
            "currentYearEUR": current_year,
            "last12MonthsEUR": last12,
            "historicalAnnualRunRateEUR": last12,
            "averageMonthlyLast12EUR": round(last12 / 12, 2),
            "receiptCount": len(receipts),
            "companyCount": len(ticker_totals),
        },
        "concentration": {
            "top5Pct": round(sum(v for _, v in ranking_pairs[:5]) / historical * 100, 2) if historical else 0,
            "top10Pct": round(sum(v for _, v in ranking_pairs[:10]) / historical * 100, 2) if historical else 0,
        },
        "byType": [{"type": t, "amountEUR": round(v, 2), "sharePct": round(v / historical * 100, 2) if historical else 0} for t, v in sorted(type_totals.items(), key=lambda x: x[1], reverse=True)],
        "goals": [{"targetEUR": g, "progressPct": round(min(last12 / g * 100, 100), 2), "remainingEUR": round(max(g - last12, 0), 2)} for g in GOALS],
        "monthly": [{"month": m, "amountEUR": round(v, 2)} for m, v in sorted(monthly.items())],
        "ranking": ranking,
        "receipts": receipts,
        "futureIncome": {
            "status": "needs_current_portfolio",
            "annualEstimateEUR": None,
            "next12MonthsEUR": None,
            "remainderCurrentYearEUR": None,
        },
    }


def write_payload(payload: dict[str, Any], output: Path, snapshot: Path | None = None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if snapshot and snapshot.exists():
        data = json.loads(snapshot.read_text(encoding="utf-8"))
        data["personalDividends"] = payload
        snapshot.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
