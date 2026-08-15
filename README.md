# Dividend Intelligence

MVP de una app iPhone centrada en dividendos y movimientos 13F.

## Qué incluye

- App SwiftUI con Inicio, Oportunidades, Smart Money, Empresas y Cartera.
- Datos JSON versionables en GitHub.
- Carga local inmediata y actualización desde GitHub mediante una URL configurable.
- Pipeline Python para comparar dos trimestres y generar movimientos y consenso.
- GitHub Action semanal para validar y regenerar los datos.

> Los datos incluidos son de demostración y aparecen identificados como tales en la app. No son asesoramiento financiero.

## Abrir la app en iPhone

Abre [DividendIntelligence.xcodeproj](DividendIntelligence.xcodeproj) en Xcode. Después:

1. Selecciona el target **Dividend Intelligence**.
2. En **Signing & Capabilities**, elige tu Apple ID en **Team**.
3. Conecta el iPhone por cable y desbloquéalo.
4. Selecciona el iPhone como destino en la barra superior.
5. Pulsa **Run** (`⌘R`).

La primera vez, iOS puede pedir activar **Modo desarrollador** en Ajustes → Privacidad y seguridad. Con una cuenta Apple gratuita, la instalación de desarrollo puede tener que renovarse periódicamente.

## Abrir como Swift Package

El proyecto mantiene Swift Package Manager para verificar el código y los modelos de forma independiente. En Xcode:

1. Abre `Package.swift`.
2. Ejecuta las pruebas del paquete. Para instalar la aplicación utiliza siempre el `.xcodeproj`.

## Datos en GitHub

La app utiliza exclusivamente el snapshot de este repositorio en GitHub. No contiene una copia offline, para evitar mostrar información antigua cuando una descarga falla. Puedes sustituir la URL definiendo `DIVIDEND_DATA_URL` en el `Info.plist`, por ejemplo:

```text
https://raw.githubusercontent.com/USUARIO/REPOSITORIO/main/data/public/snapshot.json
```

El repositorio debe ser público para usar `raw.githubusercontent.com` sin autenticación. Si debe ser privado, conviene publicar únicamente `data/public` en GitHub Pages o usar un backend con autenticación; no incluyas un token de GitHub en la app.

## Pipeline

### Descargar datos reales de EDGAR

La SEC exige que las peticiones automatizadas se identifiquen. Define un User-Agent con nombre del proyecto y correo de contacto:

```bash
export SEC_USER_AGENT="Dividend Intelligence tu-email@example.com"
python3 pipeline/sec_edgar.py \
  --investors data/config/investors.json \
  --companies data/source/companies.json \
  --current-output data/source/latest.json \
  --previous-output data/source/previous.json
```

El descargador:

- consulta `data.sec.gov/submissions/CIK##########.json`;
- selecciona los dos últimos `13F-HR` originales;
- localiza y analiza la Information Table XML de cada expediente;
- conserva CUSIP y usa ticker únicamente cuando está mapeado en `companies.json`;
- limita la frecuencia de solicitudes.

Para automatizarlo en GitHub, crea un secreto del repositorio llamado `SEC_USER_AGENT` con el mismo formato. La lista inicial de gestores está en `data/config/investors.json`.

### Construir el snapshot de la app

```bash
python3 -m unittest discover -s pipeline/tests
python3 pipeline/build_snapshot.py \
  --current data/source/latest.json \
  --previous data/source/previous.json \
  --companies data/source/companies.json \
  --output data/public/snapshot.json
```

Los archivos fuente normalizados usan CIK para el gestor y CUSIP/ticker para cada posición. Las métricas de empresas continúan siendo datos de demostración hasta conectar un proveedor financiero fiable; el snapshot mantiene `isDemo: true` para hacerlo visible en la app.

Fuentes oficiales: [API de EDGAR](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) y [acceso a datos EDGAR](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).

## Fran Score inicial

- 30% valoración
- 30% dividendo
- 20% calidad
- 20% smart money

Cada bloque se conserva en el JSON para que la puntuación sea explicable y ajustable.
