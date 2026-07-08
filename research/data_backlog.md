# Backlog de datos a incorporar (para otros días)

Series/fuentes identificadas como valiosas pero aún NO descargadas. Prioridad orientativa.
No tocar hasta agotar el valor de lo que ya tenemos (filosofía del usuario: "desentrañar").

## Liquidez de financiación / repo (foco principal — capa 2)

- ✅ **OFR — U.S. Repo Markets Data Release** (Office of Financial Research, Tesoro EE.UU.):
  **HECHO 2026-07-08.** Pipeline `ofr_repo`, tabla `ofr_repo_series`, página `/ofr-repo`.
  Tasas y volúmenes de **DVP**, **GCF** y **tri-party**, diario **2018–hoy** (más histórico del
  que temíamos, no ~2023+). API pública sin key. Ver diccionario + bitácora 2026-07-08.
- ✅ **Repo patrocinado (sponsored)** — FICC: **HECHO 2026-07-08.** Pipeline `ofr_sponsored`,
  tabla `ofr_sponsored_repo`, pestaña "Repo patrocinado" de `/repo-bilateral`. Fuente: OFR
  **Hedge Fund Monitor** (API distinta: `https://data.financialresearch.gov/hf/v1/`), series
  `FICC-SPONSORED_REPO_VOL` y `_REVREPO_VOL`, diario 2020–hoy. Canal fondos monetarios → hedge
  funds vía FICC. Se solapa en parte con el venue DVP (no sumar).
- ❌ **NCCBR** (Non-Centrally Cleared Bilateral Repo — repo bilateral sin compensar): donde vive
  el apalancamiento opaco de los hedge funds. **NO descargable vía API pública de la OFR**
  (recolección a nivel-transacción, confidencial; solo salen agregados en informes/gráficos).
  Comprobado 2026-07-08. Alternativa parcial: el libro repo de primary dealers (NYPD, abajo).
- ✅ **Volumen de SOFR y percentil 99** (NY Fed): **HECHO 2026-07-08.** Pipeline `ofr_rates`,
  tabla `ofr_reference_rates`, página `/ofr-rates`. Dataset FNYR de la OFR: SOFR/BGCR/TGCR con
  percentiles 1/25/75/99 y volumen, diario 2018–. Capta el pico de sep-2019 (SOFR P99 = 9,00%).
- ✅ **Financiación repo de primary dealers** (NY Fed, FR2004 / dataset `NYPD`): **HECHO
  2026-07-08.** Pipeline `ofr_dealer`, tabla `ofr_dealer_financing`, apartado "Primary dealers"
  de `/repo-bilateral`. RP=repo / RRP=reverse repo por colateral y tenor. Es el "repo bilateral"
  más cercano al NCCBR (~60% del reverse repo de dealers es bilateral sin compensar). **Ojo:
  discontinuado en 2021** (tras la revisión FR2004-2022 la financiación pasó al formato por venue
  ya cubierto en `ofr_repo_series`). Captura la crisis repo 2019 (pico $2,64 B).
  ⚠️ Lección: en NYPD, `AFtD`/`AFtR` **NO** son financiación sino **fails** (fallos de
  entrega/recepción); la financiación real es `RP`/`RRP`.
- **SOFR−IORB** (ya tenemos los datos: SOFR, IORB en `funding_rates`) → derivar como 2ª medida
  de escasez de reservas (probar frente a SOFR−EFFR).

## Condiciones / riesgo (basadas en precio, sin sesgo de revisión)

- **NFCI vintage** (ALFRED, archivo histórico de FRED): para cuantificar el sesgo de revisión
  del NFCI actual (look-ahead). Alta prioridad metodológica.
- **MOVE** (volatilidad implícita de bonos) — capa de liquidez de mercado en renta fija.
- **DXY / índice dólar** — dimensión global de liquidez.

## Arreglos de datos pendientes

- **GOLD y SILVER faltan en `commodity_prices`** (la rama FX de Alpha Vantage no cargó). Revisar
  el pipeline `commodity_prices`.
- **WALCL** ya está; considerar añadir M2 (masa monetaria amplia) como liquidez "cantidad".

## Estudiado y descartado (para no repetir)

- Repo tri-party por **volumen y calidad de colateral** (alta vs baja): correlación ~0 con la
  bolsa. El único con señal fue el **haircut** (`repo_haircut`), y solo en BTC.
- Concentración top-3 y split overnight/term del repo: vacíos/planos en la DB.
- Emisión de letras (flujo, stock, neta): sin señal directa de timing (ver research_log).
