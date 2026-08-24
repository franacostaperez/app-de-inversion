#!/usr/bin/env python3
"""Ensure every reported company has a cautious qualitative profile."""

from __future__ import annotations

import argparse
import json
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path


SECTOR_MODELS = {
    "Technology": ("Vende tecnología, software, semiconductores o servicios digitales; puede combinar licencias, suscripciones, consumo y soporte.", "La propiedad intelectual, la integración del ecosistema, la escala y los costes de cambio pueden proteger la relación con el cliente."),
    "Financials": ("Genera ingresos mediante margen de intereses, comisiones, gestión de activos, seguros u otros servicios financieros.", "La regulación, la escala de financiación, los datos, la distribución y las relaciones recurrentes pueden constituir barreras de entrada."),
    "Healthcare": ("Obtiene ingresos de medicamentos, dispositivos, diagnósticos o servicios sanitarios, normalmente mediante venta directa y reembolso público o privado.", "Las patentes, la evidencia clínica, las autorizaciones regulatorias y las relaciones médicas pueden proteger el negocio."),
    "Industrials": ("Vende equipos, componentes, proyectos y servicios industriales; la posventa y el mantenimiento pueden aportar ingresos recurrentes.", "La ingeniería, las certificaciones, la base instalada y las relaciones de largo plazo pueden elevar el coste de sustitución."),
    "Consumer Staples": ("Vende productos de consumo frecuente a través de minoristas, distribuidores y canales directos, con ingresos ligados a volumen, precio y mezcla.", "La marca, la distribución, la escala de compra y el hábito de consumo pueden sostener poder de precios y cuota."),
    "Consumer Discretionary": ("Vende productos o servicios de consumo discrecional mediante tiendas, distribuidores o canales digitales; monetiza volumen, precio y mezcla.", "La marca, la experiencia, la distribución y la escala pueden aportar diferenciación, aunque suelen ser sensibles al ciclo."),
    "Energy": ("Genera ingresos produciendo, procesando, transportando o suministrando energía y servicios asociados; los resultados dependen de volúmenes, precios y contratos.", "Los activos, reservas, permisos, contratos, escala y regulación pueden actuar como barreras."),
    "Real Estate": ("Genera rentas, ocupación y servicios a partir de activos inmobiliarios, financiados con capital y deuda.", "Las ubicaciones, la escala, el coste de capital y las relaciones con inquilinos pueden diferenciar la cartera."),
    "Utilities": ("Cobra por suministrar electricidad, gas, agua u otros servicios esenciales mediante tarifas reguladas y contratos.", "Las concesiones, redes físicas y autorizaciones regulatorias crean barreras elevadas y flujos relativamente previsibles."),
    "Communication Services": ("Monetiza conectividad, contenido, publicidad o servicios de comunicación mediante suscripciones, consumo y venta de espacios publicitarios.", "La red, la audiencia, los derechos de contenido, el espectro y la escala pueden generar efectos de red y costes de cambio."),
}

INDUSTRY_SECTOR_HINTS = (
    (("BANK", "LOAN", "FINANCE", "INVESTMENT ADVICE", "BROKER"), "Financials"),
    (("INSURANCE",), "Financials"),
    (("PHARMACEUTICAL", "BIOLOGICAL", "MEDICINAL", "MEDICAL", "HEALTH"), "Healthcare"),
    (("SEMICONDUCTOR", "SOFTWARE", "COMPUTER", "ELECTRONIC", "DATA PROCESSING"), "Technology"),
    (("OIL", "GAS", "PETROLEUM", "DRILLING", "COAL"), "Energy"),
    (("ELECTRIC", "NATURAL GAS DISTRIBUTION", "WATER SUPPLY"), "Utilities"),
    (("REAL ESTATE", "REIT"), "Real Estate"),
    (("RETAIL", "APPAREL", "RESTAURANT", "HOTEL", "MOTOR VEHICLE"), "Consumer Discretionary"),
    (("FOOD", "BEVERAGE", "TOBACCO", "SOAP", "GROCERY"), "Consumer Staples"),
    (("TELEPHONE", "COMMUNICATION", "BROADCAST", "CABLE", "MOTION PICTURE"), "Communication Services"),
    (("MACHINERY", "EQUIPMENT", "CONSTRUCTION", "TRANSPORTATION", "AIRCRAFT", "INDUSTRIAL"), "Industrials"),
)


def inferred_sector(sector: str | None, industry: str | None) -> str | None:
    if sector:
        return sector
    normalized = (industry or "").upper()
    return next((candidate for hints, candidate in INDUSTRY_SECTOR_HINTS if any(hint in normalized for hint in hints)), None)


def fallback_profile(holding: dict, market: dict) -> dict:
    name = market.get("name") or holding.get("company") or "Empresa"
    industry = market.get("industry")
    sector = inferred_sector(market.get("sector"), industry)
    activity = industry or sector
    description = market.get("description")
    if not description and activity:
        description = (
            f"{name} opera principalmente en la industria de {activity.lower()}. "
            "Su actividad se analiza a partir de la clasificación oficial del emisor en la SEC y se complementa "
            "con sus informes financieros y la información pública de mercado disponible."
        )
    if not description:
        description = (
            f"{name} es un emisor o instrumento identificado en las carteras 13F monitorizadas. "
            "Todavía no existe una descripción pública suficientemente verificable de su actividad; la ficha evita "
            "atribuirle un negocio que no haya podido confirmarse."
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
        "businessModel": (
            f"{name} opera en {activity or 'un mercado pendiente de clasificación detallada'}. Su modelo combina los activos, el personal, la tecnología "
            "y los canales de distribución necesarios para entregar su propuesta de valor, retener clientes y reinvertir en crecimiento."
        ),
        "revenueModel": f"{name}: {revenue} Conviene vigilar la recurrencia, la concentración de clientes y la capacidad de trasladar costes a precios.",
        "economicMoat": f"Ventajas competitivas potenciales: {moat} Su durabilidad debe confirmarse con márgenes, retornos y cuota de mercado a lo largo del ciclo.",
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
        else:
            existing = by_cusip[cusip]
            placeholders = {
                "description": "La información financiera y los informes oficiales se actualizan automáticamente en la ficha.",
                "businessModel": "Opera en ",
                "revenueModel": "Genera ingresos mediante la venta de sus productos",
                "economicMoat": "No existe información suficiente para confirmar un foso defensivo",
            }
            for key, marker in placeholders.items():
                if not existing.get(key) or marker in existing.get(key, ""):
                    existing[key] = generated[key]
            if not existing.get("investorRelationsURL"):
                existing["investorRelationsURL"] = generated["investorRelationsURL"]
                existing["investorRelationsVerified"] = generated["investorRelationsVerified"]
    result = sorted(by_cusip.values(), key=lambda item: item.get("name", ""))
    args.qualitative_database.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(f"Qualitative profiles: {len(result)}; added: {len(result) - len(qualitative)}")


if __name__ == "__main__":
    main()
