# Mis Dividendos · XTB

`Dividendos` del Google Sheet **Registro de dividendos XTB** es la fuente de verdad para efectivo realmente cobrado. El pipeline no infiere cobros a partir de calendarios ni mezcla dividendos anunciados con dividendos recibidos.

## Flujo

1. La automatización personal Gmail → Google Sheet registra los avisos de XTB y deduplica por `ID aviso`.
2. `sync-xtb-dividends.yml` lee el tab `Dividendos` una vez al día.
3. `pipeline/xtb_dividends.py` normaliza y calcula métricas sin usar IA.
4. Se publica `data/public/xtb-dividends.json` y se inyecta `personalDividends` en `snapshot.json`.
5. Los demás rebuilds preservan esa capa independiente mediante `pipeline/preserve_personal_dividends.py`.

Esto aplica el principio **AI only on change**: la importación, deduplicación, agregación, objetivos y concentración son deterministas y consumen 0 tokens de ChatGPT.

## Configuración de GitHub

El Sheet permanece privado. Crear un service account de Google con acceso de solo lectura, compartir el spreadsheet con su correo como Viewer y guardar el JSON del service account en el secreto del repositorio `GOOGLE_SERVICE_ACCOUNT_JSON`.

Opcionalmente puede definirse la variable `XTB_DIVIDENDS_SHEET_ID`; si no existe se usa el ID actual del registro XTB. No se debe publicar ni incorporar la credencial al repositorio o al cliente.

## Datos publicados

- total histórico y año actual;
- cobrado en los últimos 12 meses y run-rate histórico;
- promedio mensual de 12 meses;
- evolución mensual;
- acciones frente a ETF;
- concentración Top 5 / Top 10;
- ranking por ticker;
- objetivos de 1.000 / 2.000 / 5.000 / 10.000 EUR;
- histórico de cobros con ID del aviso para trazabilidad.

## Renta futura

`futureIncome` queda separado del histórico. Mientras Dividend Intelligence no tenga una fuente fiable de **cantidades actuales de la cartera personal**, el estado es `needs_current_portfolio` y los importes futuros son `null`.

No se anualiza silenciosamente el último dividendo ni se supone que las posiciones históricas sigan en cartera. Cuando se conecten las posiciones actuales, la estimación combinará cantidades actuales con dividendos confirmados/estimados y conservará los niveles de confianza `Confirmado`, `Estimado` e `Incierto`.
