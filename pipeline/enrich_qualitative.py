#!/usr/bin/env python3
"""Ensure every reported company has a cautious qualitative profile."""

from __future__ import annotations

import argparse
import json
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path


SECTOR_MODELS = {
    "Technology": ("Vende tecnología, software, semiconductores o servicios digitales.", "Propiedad intelectual, integración, escala y costes de cambio pueden generar ventajas."),
    "Financials": ("Genera ingresos mediante intereses, comisiones y servicios financieros.", "Regulación, escala, financiación, datos y relaciones pueden constituir barreras."),
    "Healthcare": ("Obtiene ingresos de medicamentos, dispositivos, pruebas o servicios sanitarios.", "Patentes, evidencia clínica, regulación y relaciones médicas pueden proteger el negocio."),
    "Industrials": ("Vende equipos, proyectos y servicios industriales o de infraestructura.", "Ingeniería, certificaciones, activos y relaciones de largo plazo pueden diferenciarla."),
    "Consumer Staples": ("Vende productos de consumo frecuente mediante canales minoristas y distribuidores.", "Marca, distribución, escala y hábito de compra pueden sostener su posición."),
    "Consumer Discretionary": ("Vende productos o servicios de consumo sujetos a gasto discrecional.", "Marca, experiencia, distribución y escala pueden aportar una ventaja."),
    "Energy": ("Genera ingresos produciendo, procesando o suministrando energía y servicios asociados.", "Activos, reservas, contratos, escala y regulación pueden actuar como barreras."),
    "Real Estate": ("Genera rentas y servicios a partir de activos inmobiliarios.", "Ubicaciones, escala, coste de capital y relaciones con inquilinos pueden diferenciarla."),
    "Utilities": ("Cobra por suministrar servicios esenciales mediante infraestructura regulada.", "Concesiones, redes físicas y regulación crean barreras elevadas."),
    "Communication Services": ("Monetiza conectividad, contenido, publicidad o servicios de comunicación.", "Red, audiencia, contenido, espectro y escala pueden generar ventajas."),
}


def fallback_profile(holding: dict, market: dict) -> dict:
    name = market.get("name") or holding.get("company") or "Empresa"
    sector = market.get("sector") or "sector no clasificado"
    industry = market.get("industry")
    description = market.get("description") or (
        f"{name} desarrolla su actividad en {industry or sector}. "
        "La información financiera y los informes oficiales se actualizan automáticamente en la ficha."
    )
    revenue, moat = SECTOR_MODELS.get(sector, (
        "Genera ingresos mediante la venta de sus productos, servicios o activos a clientes de su mercado.",
        "No existe información suficiente para confirmar un foso defensivo; debe verificarse su marca, escala, costes de cambio y retornos sobre el capital.",
    ))
    investor_url = market.get("investorRelationsURL") or (
        "https://www.google.com/search?q=" + urllib.parse.quote_plus(name + " investor relations")
    )
    return {
        "cusip": holding["cusip"],
        "ticker": market.get("ticker"),
        "name": name,
        "source": market.get("source", "SEC EDGAR · Google Finance · Yahoo Finance respaldo"),
        "status": "qualitative",
        "updatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "description": description,
        "businessModel": f"Opera en {industry or sector} y organiza sus activos, tecnología y distribución para atender a sus clientes.",
        "revenueModel": revenue,
        "economicMoat": moat,
        "investorRelationsURL": investor_url,
        "investorRelationsVerified": bool(market.get("investorRelationsVerified")),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--holdings", type=Path, required=True)
    parser.add_argument("--company-database", type=Path, required=True)
    parser.add_argument("--qualitative-database", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.holdings.read_text())
    market = {item["cusip"]: item for item in json.loads(args.company_database.read_text())}
    qualitative = json.loads(args.qualitative_database.read_text()) if args.qualitative_database.exists() else []
    by_cusip = {item["cusip"]: item for item in qualitative}
    holdings = {}
    for investor in source.get("investors", []):
        for holding in investor.get("holdings", []):
            holdings.setdefault(holding["cusip"], holding)
    # Keep profiles complete for the entire known company catalogue, including
    # companies that have moved out of the latest 13F reporting window.
    for cusip, company in market.items():
        holdings.setdefault(cusip, {
            "cusip": cusip,
            "company": company.get("name") or company.get("ticker") or "Empresa",
        })
    for cusip, holding in holdings.items():
        generated = fallback_profile(holding, market.get(cusip, {}))
        if cusip not in by_cusip:
            by_cusip[cusip] = generated
        elif not by_cusip[cusip].get("investorRelationsURL"):
            by_cusip[cusip]["investorRelationsURL"] = generated["investorRelationsURL"]
            by_cusip[cusip]["investorRelationsVerified"] = generated["investorRelationsVerified"]
    result = sorted(by_cusip.values(), key=lambda item: item.get("name", ""))
    args.qualitative_database.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(f"Qualitative profiles: {len(result)}; added: {len(result) - len(qualitative)}")


if __name__ == "__main__":
    main()
