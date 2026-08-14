# Dividend Intelligence

MVP de una app iPhone centrada en dividendos y movimientos 13F.

## Qué incluye

- App SwiftUI con Inicio, Oportunidades, Smart Money, Empresas y Cartera.
- Datos JSON versionables en GitHub.
- Carga local inmediata y actualización desde GitHub mediante una URL configurable.
- Pipeline Python para comparar dos trimestres y generar movimientos y consenso.
- GitHub Action semanal para validar y regenerar los datos.

> Los datos incluidos son de demostración y aparecen identificados como tales en la app. No son asesoramiento financiero.

## Abrir la app

El proyecto usa Swift Package Manager para que el código y los modelos sean verificables sin archivos generados. En Xcode:

1. Abre `Package.swift`.
2. Selecciona un simulador de iPhone.
3. Ejecuta el producto `DividendIntelligenceApp`.

Para una distribución normal en App Store, crea un proyecto iOS llamado `DividendIntelligence` y añade el target local `DividendIntelligenceKit`; la entrada de la app está en `App/DividendIntelligenceApp.swift`.

## Datos en GitHub

La app busca primero el snapshot incluido en `Sources/DividendIntelligenceKit/Resources/snapshot.json`. Para apuntarla a GitHub define `DIVIDEND_DATA_URL` en el `Info.plist`, por ejemplo:

```text
https://raw.githubusercontent.com/USUARIO/REPOSITORIO/main/data/public/snapshot.json
```

El repositorio debe ser público para usar `raw.githubusercontent.com` sin autenticación. Si debe ser privado, conviene publicar únicamente `data/public` en GitHub Pages o usar un backend con autenticación; no incluyas un token de GitHub en la app.

## Pipeline

```bash
python3 -m unittest discover -s pipeline/tests
python3 pipeline/build_snapshot.py \
  --current data/source/2026-Q2.json \
  --previous data/source/2026-Q1.json \
  --companies data/source/companies.json \
  --output data/public/snapshot.json
```

Los archivos fuente normalizados usan CIK para el gestor y CUSIP/ticker para cada posición. La siguiente fase conectará el descargador directamente con EDGAR, respetando la política de identificación y límites de la SEC.

## Fran Score inicial

- 30% valoración
- 30% dividendo
- 20% calidad
- 20% smart money

Cada bloque se conserva en el JSON para que la puntuación sea explicable y ajustable.

