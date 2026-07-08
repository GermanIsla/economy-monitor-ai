# Backlog de datos a incorporar (para otros días)

Series/fuentes identificadas como valiosas pero aún NO descargadas. Prioridad orientativa.
No tocar hasta agotar el valor de lo que ya tenemos (filosofía del usuario: "desentrañar").

## Liquidez de financiación / repo (foco principal — capa 2)

- ✅ **OFR — U.S. Repo Markets Data Release** (Office of Financial Research, Tesoro EE.UU.):
  **HECHO 2026-07-08.** Pipeline `ofr_repo`, tabla `ofr_repo_series`, página `/ofr-repo`.
  Tasas y volúmenes de **DVP**, **GCF** y **tri-party**, diario **2018–hoy** (más histórico del
  que temíamos, no ~2023+). API pública sin key. Ver diccionario + bitácora 2026-07-08.
- **Repo patrocinado (sponsored)** — FICC/DTCC: canal fondos monetarios → hedge funds. El
  `Sponsored GC` que ya tenemos solo llega a dic-2024; OFR/FICC tiene más.
- **NCCBR** (Non-Centrally Cleared Bilateral Repo — repo bilateral sin compensar): donde vive
  el apalancamiento opaco de los hedge funds. Recolección OFR muy reciente.
- **Volumen de SOFR y percentil 99** (NY Fed): los picos de tensión que el nivel medio esconde.
- **Posiciones y financiación de primary dealers** (NY Fed, formulario FR2004).
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
