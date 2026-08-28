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

### Numantia y carteras CNMV

En **Fondos → Carteras CNMV → Numantia Patrimonio Global** se muestra el
informe del primer semestre de 2026: 27 acciones, sus valores en euros,
pesos sobre el patrimonio, 9 incorporaciones y 10 posiciones que dejan de
figurar frente al 31/12/2025. Cada posición enlaza sus fuentes de mercado.

La fuente versionada está en `data/fund-portfolios/numantia/2026-H1.json`.
`build_snapshot.py` incorpora automáticamente el informe más reciente por fondo
en `fundPortfolios`, incluso después de una actualización de EDGAR. El campo es
complementario: no modifica los 13F ni el consenso basado en cantidades de acciones.
El informe CNMV no publica cantidades de títulos ni precios de compra. No se
estiman ni se confunden cambios de valoración con operaciones.

Los dividendos TTM utilizan pagos efectivamente realizados en los 12 meses hasta
la fecha del precio; se excluyen pagos futuros. Las métricas se guardan con fecha,
divisa y fuentes propias. N/D significa no disponible/no fiable; N/M, pérdidas.
La importación de un informe no actualiza por sí misma las métricas de mercado.

**Esta sección requiere compilar e instalar la versión actualizada de la app.**
Las versiones anteriores siguen leyendo el snapshot, pero ignoran el nuevo campo.
No se ha cambiado la programación ni el universo del monitor de 13F.

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

### Base de datos de empresas

Los perfiles enriquecidos se guardan en `data/companies/index.json`. Cada actualización detecta empresas nuevas en los 13F y procesa hasta cinco por ejecución para respetar los límites del proveedor. Configura el secreto `ALPHA_VANTAGE_API_KEY` en GitHub; la clave nunca se incorpora a la app ni al repositorio.

Los perfiles pueden incluir descripción, sector, industria, país, capitalización, dividendos, yield, PER y EPS. Si una búsqueda de símbolo no alcanza la confianza mínima, la empresa queda pendiente en lugar de asociarse automáticamente a una compañía incorrecta.

### Construir el snapshot de la app

```bash
python3 -m unittest discover -s pipeline/tests
python3 pipeline/build_snapshot.py \
  --current data/source/latest.json \
          --previous data/source/previous.json \
          --companies data/source/companies.json \
          --company-database data/companies/index.json \
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

### Escala exigente de margen operativo (28/08/2026)

El score de oportunidades usa un componente de margen de **12 puntos sobre 100**.
No se cambia su peso ni los otros componentes. La escala se endurece: hasta 5 %
no aporta puntos; 10 % aporta 2; 15 % aporta 5; 20 % aporta 7; 25 % aporta 10;
y desde 30 % aporta los 12 puntos. Se interpola y redondea primero el nivel
0–10 y después se pondera a 12. El máximo se reserva a márgenes de al menos 30 %.
Un margen ausente mantiene el score incompleto, no se interpreta como margen cero.

Regresión del cambio de margen: Booz Allen (BAH), margen operativo 9,21 %, pasa de
6 a 2 puntos de margen; conservando la valoración anterior, de 67 a 63 puntos totales.

### Escala exigente de valoración (28/08/2026)

La valoración mantiene **35 puntos sobre 100**, usando el mismo PER verificado
que ya figuraba en el score. No se sustituye por PER forward ni se actualizan
precios o beneficios al recalcular.

| PER | Puntos base / 35 |
|---|---:|
| Positivo, ≤8x | 35 |
| 10x | 30 |
| 12x | 24 |
| 15x | 16 |
| 18x | 10 |
| 20x | 7 |
| 25x | 2 |
| ≥30x | 0 |

Se interpola y redondea entre niveles. Un PER superior a 8x nunca recibe el
máximo, aunque el redondeo lo acerque. El sector y la marca **no bonifican** la
puntuación base: la referencia ajustada solo determina una penalización
adicional si se supera. Esa penalización es 0 en 1,00x la referencia, 2 en
1,15x, 5 en 1,35x, 8 en 1,65x y 12 desde 2,00x, interpolando entre niveles.
El resultado no puede ser negativo. PER ausente o no significativo aporta cero;
el score incompleto continúa sin publicarse. Un PER bajo no garantiza calidad
ni descarta beneficios extraordinarios o un pico del ciclo.

Con los datos existentes de Booz Allen (PER 11,8x y referencia 12x), la valoración
pasa de 33 a 25 puntos y, tras el endurecimiento previo del margen, el total pasa
de 63 a 55. Los demás componentes y datos permanecen iguales.

El workflow `Rebuild app snapshot` reconstruye y verifica los datos públicos
cuando cambia la fórmula o una cartera CNMV, sin descargar ni sustituir las
fuentes SEC existentes. Las métricas de Numantia son una consulta fechada,
no cotizaciones en tiempo real ni una actualización automática de dividendos.
