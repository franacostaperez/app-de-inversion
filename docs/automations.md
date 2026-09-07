# Automatizaciones de Dividend Intelligence

## Frecuencias y dependencias

Todos los horarios son UTC. En Atlantic/Canary se suma una hora en verano y
ninguna en invierno. Los cron son orientativos: GitHub puede retrasar su inicio.

| Workflow | Antes | Ahora | Propósito y dependencias |
|---|---|---|---|
| `update-prices.yml` | Dentro del proceso completo, dos veces al día | Diario 07:17 y 19:17 | Cotización y PER trailing de los tickers verificados del catálogo. Reutiliza los endpoints ligeros existentes de Yahoo; no descarga históricos de cinco años, informes, 13F ni calendarios. |
| `update-dividends.yml` | Dos veces al día | Sábado 08:17; manual; cambios en configuración IR | Próximos dividendos y anuncios/cambios, horizonte de 180 días, fuentes y límites existentes: IR 30, SEC 60, Alpha Vantage 20. Conserva ECB para conversión a EUR. Publica snapshot completo y compacto juntos. |
| `update-sec-reports.yml` | Dos veces al día | Diario 05:17; manual | Detecta filings de las empresas del catálogo. El extractor existente descarga companyfacts solo si hay informes nuevos, ausentes o con versión antigua. |
| `update-13f.yml` | Dos veces al día | Martes y viernes 03:17; manual; cambios en inversores | Últimos 13F y archivos históricos, comparación trimestral y resolución CUSIP/FIGI. Las empresas nuevas se enriquecen en el siguiente ciclo semanal. |
| `update-data.yml` | Todos los procesos, 07:17 y 19:17 | Sábado 02:17; manual; cambios en cartera | S&P 500, FTSE 100, enriquecimiento completo, perfiles cualitativos, históricos FTSE y auditorías profundas. Los informes SEC tienen su ciclo diario independiente. |
| `rebuild-snapshot.yml` | Algunos cambios de código/CNMV; manual | Cambios de entradas del snapshot o su generador en main; manual | Reconstrucción local con el scoring existente y auditorías. No consulta proveedores. |
| `refresh-ftse-analysis.yml` | Manual y cambios del propio workflow | Solo manual | Recuperación puntual de históricos FTSE, snapshot si cambian las entradas y auditorías. Usa el mismo bloqueo de escritura. |
| `validate-app.yml` | Push/PR | Push/PR y manual | Tests Python, validación de workflows y compilación iOS. Cancela únicamente validaciones obsoletas de su propia rama. |
| `data-pipeline.yml` | No existía | Reutilizable, sin programación propia | Ejecución común, control de cambios y publicación atómica de datos. |
| `fix-dividend-amount-parser.yml` | Push del workflow, YAML inválido | Solo manual | Se conserva porque la reparación por acción aún NO está integrada. Ejecuta el script extraído y sus tests antes de publicar el fix. No se ejecuta durante esta reorganización. |
| `inspect-dividend-events.yml` | Diagnóstico al cambiar el workflow | Eliminado | No actualizaba datos. La inspección se puede hacer leyendo `data/public/snapshot.json`; su contenido anterior sigue en Git. |

XTB/Gmail sigue fuera del repositorio. No se ha modificado ninguna automatización
ChatGPT, incluida cualquier revisión 13F que exista allí.

El pipeline actual no tiene PER forward ni fuente de beneficios forward:
se conserva PER trailing y no se inventa una nueva métrica. Las derivadas del
precio (rentabilidad por dividendo con la base conocida y distancia a la media
ya almacenada) se actualizan localmente sin nuevas descargas de fundamentales.
La comprobación cruzada completa de proveedores sigue en el ciclo semanal.

## Publicación y eliminación de trabajo redundante

`pipeline/run_automation.py` registra una huella de las entradas reales en
`data/automation/state.json`. Incluye nuevos archivos no rastreados, informes,
catálogos, valoración, carteras y el generador. Ignora únicamente `generatedAt`
y `updatedAt`, que son marcas de regeneración, no fechas efectivas de filings.

Si no cambia la huella, no reconstruye snapshot ni scoring. Cuando cambia,
reutiliza el generador completo local existente (unos cuatro segundos en la
verificación inicial), manteniendo exactamente sus fórmulas. No se implementa un
segundo scoring parcial que pueda divergir. Una reconstrucción manual o un cambio
del generador fuerza la ejecución. Las auditorías profundas solo se realizan en
los ciclos semanal, reconstrucción explícita y recuperación FTSE.

Los eventos de dividendos se actualizan independientemente de esa huella y se
escriben tanto en `snapshot.json` como en `snapshot-core.json`; no fuerzan scoring.
Todos los resultados y registros de frescura se publican en un solo commit.
Los commits del `GITHUB_TOKEN` no disparan otros workflows por push: por eso cada
productor invoca explícitamente la reconstrucción condicional antes de publicar.

Todos los escritores comparten `dividend-data-<rama>`, sin cancelar el trabajo
activo y con `queue: max` para no sustituir ejecuciones pendientes de otro ciclo.
El checkout obtiene la punta de la rama después de adquirir el bloqueo. Un push
humano concurrente provoca un rechazo seguro al publicar; se debe repetir el
workflow. No se rebasa un snapshot calculado sobre entradas antiguas.

`queue: max` está soportado por GitHub desde mayo de 2026:
[documentación oficial](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).
Actionlint 1.7.12 aún no conoce esa clave; la validación excluye exclusivamente
ese diagnóstico y comprueba el resto de sintaxis y expresiones. La aceptación y
la cola también se verifican mediante ejecuciones reales en GitHub Actions.

## Operación, límites y recuperación

- `data/automation/state.json` conserva la última ejecución completada de cada
  ciclo y si regeneró el snapshot. No usar `snapshot.generatedAt` para deducir
  que todos los tipos de datos se actualizaron a la vez.
- `data/automation/quotes.json` registra tickers consultados, respuestas de
  precios/PER y ausencias. Una caída total de precios o PER falla el job antes de
  publicar. Una ausencia parcial conserva el dato anterior y queda identificada.
- Yahoo se consulta con cuatro trabajadores, deduplicando tickers; conserva los
  filtros de títulos no cotizables. Los proveedores pueden limitar peticiones.
- Los límites de cobertura del calendario son los anteriores; semanal implica
  hasta siete días de demora en anuncios. Su conversión ECB también es semanal.
- 13F mantiene frecuencia uniforme dos veces por semana. Para intensificar las
  ventanas de presentación se puede lanzar manualmente o cambiar temporalmente
  el cron a diario; no se introduce lógica estacional adicional.
- La reparación pendiente del parser se conserva manual porque su comprobación
  confirmó que la expresión amplia y la ausencia del test de importes agregados
  siguen en producción. Su implementación está en
  `pipeline/maintenance/harden_dividend_parser.py`. Tras aplicarla y validar
  el resultado, se podrá eliminar el workflow. Esta reorganización no aplica
  silenciosamente ese cambio de lógica.

Para recuperar un ciclo: Actions → workflow correspondiente → Run workflow.
`rebuild-snapshot.yml` regenera y audita solo datos locales. `update-data.yml`
realiza el mantenimiento semanal completo; no sustituye las revisiones 13F,
SEC o calendario que ahora tienen sus propias acciones.

## Verificación

```sh
python3 -m unittest discover -s pipeline/tests
python3 pipeline/run_automation.py rebuild
actionlint -ignore 'unexpected key "queue" for "concurrency" section'
```

Los tests cubren ausencia de nuevas entradas, nuevos archivos, cambios de datos,
fallos de cotización, conservación de fundamentales y publicación simultánea
del calendario en snapshot completo/compacto. `validate-app.yml` comprueba
además la compilación de la app en macOS.
