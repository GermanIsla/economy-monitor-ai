# Diccionario de datos

Catálogo de las series disponibles en la base de datos, orientado al estudio
liquidez↔bolsa. La columna **clave** es el identificador que usa el motor
`research/analysis` para cargar la serie.

> **Convención de dirección:** "↑ = más liquidez / risk-on" facilita interpretar
> correlaciones. Cuando una serie va al revés (más alto = menos liquidez), se marca.

---

## Variables objetivo (bolsa)

| clave | Serie | Símbolo DB | Tabla / columna | Frecuencia | Unidad | Rango | Notas |
|---|---|---|---|---|---|---|---|
| `sp500` | S&P 500 | `^GSPC` | `market_indices.close_price` | Diaria (días hábiles) | Puntos de índice | 1927– | Nivel del índice, sin dividendos. Cierre de sesión NY. |
| `btc` | Bitcoin | `BTC-USD` | `market_indices.close_price` | Diaria (24/7) | USD | 2014– | Cotiza fines de semana; al resamplear a semanal se toma el cierre. Alta beta a liquidez. |

---

## Liquidez y condiciones financieras (explicativas)

| clave | Serie | ID DB | Tabla / columna | Frecuencia | Unidad | Dirección | Rango | Notas |
|---|---|---|---|---|---|---|---|---|
| `fed_treast` | Tesoros en cartera Fed | `TREAST` | `fed_balance_assets.value` | Semanal (miércoles) | **Millones USD (10⁶)** | ↑ = más liquidez | 2002– | H.4.1 Securities Held Outright. |
| `fed_feddt` | Deuda de agencias Fed | `FEDDT` | `fed_balance_assets.value` | Semanal (miércoles) | **Millones USD** | ↑ = más liquidez | 2002– | Residual, ~0 desde 2014. |
| `fed_mbs` | MBS en cartera Fed | `WSHOMCB` | `fed_balance_assets.value` | Semanal (miércoles) | **Millones USD** | ↑ = más liquidez | 2002– | Clave en QE3 y COVID. |
| `fed_soma` | Securities Held Outright (suma) | — | suma de las 3 anteriores | Semanal | **Millones USD** | ↑ = más liquidez | 2002– | Proxy del tamaño de la cartera de la Fed (derivada en código, no es una fila de DB). |
| `nfci` | NFCI (Chicago Fed) | `NFCI` | `nfci_readings.value` | Semanal | Índice z (media 0) | **↑ = condiciones MÁS RESTRICTIVAS** (menos liquidez) → **invertir** | 1971– | Signo opuesto al resto. Al correlacionar con bolsa, esperar signo negativo o invertir la serie. |
| `nfci_credit` | NFCI Credit | `NFCICREDIT` | `nfci_readings.value` | Semanal | Índice z | ↑ = crédito más restrictivo → invertir | 1971– | Subíndice de crédito. |
| `walcl` | Balance total Fed | `WALCL` | `liquidity_series.value` | Semanal (miércoles) | Millones USD | ↑ = más liquidez | 2003– | Balance **completo** (incluye préstamos, repos, swaps), no solo la cartera de compras. |
| `tga` | Treasury General Account | `WTREGEN` | `liquidity_series.value` | Semanal | Millones USD | **↓ = más liquidez** (drena al subir) | 2003– | Caja del Tesoro en la Fed. |
| `rrp` | Reverse Repo overnight | `RRPONTSYD` | `liquidity_series.value` | **Diaria** | Millones USD (norm.) | **↓ = más liquidez** (drena al subir) | 2003– | FRED lo da en miles de millones; el pipeline lo pasa a millones (×1000). |
| `net_liquidity` | Liquidez neta (derivada) | — | `walcl − tga − rrp` (en `analysis`) | Semanal | Millones USD | ↑ = más liquidez | 2003– | Serie derivada en código; alinea los 3 componentes a W-FRI antes de restar. |
| `reserves` | Reservas bancarias | `WRESBAL` | `liquidity_series.value` | Semanal | Millones USD | ↑ = más liquidez | 2003– | La liquidez "cantidad" utilizable. **Mejor proxy que `fed_soma`**, que es un driver, no liquidez. |

### Liquidez de financiación — capa 2 (tabla `funding_rates`) · FOCO DEL USUARIO

| clave | Serie | ID FRED | Frecuencia | Dirección | Notas |
|---|---|---|---|---|---|
| `sofr` | SOFR (repo con colateral) | `SOFR` | Diaria | — | 2018–. Tipo repo garantizado. |
| `funding_stress` | Estrés financiación (SOFR−EFFR) | derivada | Diaria | ↑ = escasez = risk-off (−1) | 2018–. Capta el pico repo de sep-2019 (SOFR 2,95%). **Variable episódica/umbral**: la correlación lineal con la bolsa ≈ 0; la señal está en los **picos**, no en el nivel medio → requiere análisis de eventos/umbral, no correlación lineal. |

*(EFFR e IORB también en `funding_rates`; sirven para spreads. IORB solo desde 2021.)*

### Señales de mercado basadas en precio (tabla `market_signals`, sin sesgo de revisión)

| clave | Serie | ID FRED | Frecuencia | Dirección (prov.) | Transf. | Notas |
|---|---|---|---|---|---|---|
| `credit` | Spread crédito Baa−10a | `BAA10Y` | Diaria | **nivel alto = prima de riesgo → retorno futuro + (+1)** | **level** | 1990–. En nivel funciona (contrarian); en cambios era ruido. Fuerte post-2020; **la mejor señal para BTC** a 26s. Sustituye al HY OAS de ICE (solo 2023+ en FRED). |
| `curve` | Curva de tipos 10a−2a | `T10Y2Y` | Diaria | ↑ = reflación (+1, **ambiguo**) | level | 1990–. Su señal real es de recesión a horizonte largo. |
| `vix` | VIX | `VIXCLS` | Diaria | nivel alto → retorno futuro + (+1) | level | 1990–. En **cambios** es coincidente-negativo; en **nivel** es prima de riesgo. |

### ⚠️ Trampas conocidas

- **Unidad del balance Fed:** el docstring de `db/models/fed_balance.py` dice "miles de
  millones (MM USD)" pero **los datos están en millones USD** (unidad nativa de FRED). TREAST
  ≈ 5.771.393 = $5,77 billones. No multiplicar/dividir asumiendo "miles de millones".
- **Signo del NFCI:** es la única serie donde "más alto" significa **menos** liquidez.
- **Frescura NFCI:** al escribir esto el último dato es 2026-03-20 (el pipeline puede estar
  algo atrasado). Verificar antes de usar como serie "en tiempo real".
- **Fines de semana BTC vs S&P:** BTC tiene datos sáb/dom, el S&P no. El resampleo semanal
  (W-FRI) lo neutraliza.

---

## Actividad de mercado y ciclo real (cableadas al motor)

| clave | Serie | Origen | Frecuencia | Dirección | Construcción / notas |
|---|---|---|---|---|---|
| `bill_issuance` | Emisión de T-bills (flujo) | `treasury_auctions` (Bill) | Semanal | ↑ = más liquidez (hipótesis) | Suma semanal de `total_accepted` **suavizada a 4 semanas**. Emisión **bruta** (no neta). En USD. |
| `bills_outstanding` | Letras en circulación (stock) | `treasury_auctions` (Bill) | Semanal | ↑ = más liquidez (hipótesis) | Reconstruido: +importe al emitir, −al vencer, acumulado, truncado en la última emisión. ~$6,9B máx. Es la serie que "se parece" a la bolsa **en nivel**. |
| `repo_total` | Volumen repo tri-party | `repo_operations` (Total) | **Mensual** | ↑ = más actividad | 191 puntos (2010–2026-03). Miles de millones USD. |
| `repo_risk_share` | % colateral repo de riesgo | `repo_operations` | **Mensual** | ↑ = más apetito de riesgo | (Equities+Corporates+ABS+CDOs+Whole Loans+Munis+Internac.+Other) / Total. |
| `repo_haircut` | Haircut colateral de riesgo | `repo_operations.margin_median` | **Mensual** | ↑ = menos apalancamiento = risk-off (−1) | Media del haircut (recorte) de Equities/Corporates Non-IG/ABS Non-IG/CDOs/CMO PL Non-IG. **Sin señal en S&P; negativa persistente en BTC** (−0,24 a 3m post-2020). En máximos ahora (2024-25). |
| `wti` | Petróleo WTI | `commodity_prices` (WTI) | Semanal | ↑ = ciclo/crecimiento | Limpio, 1986–. USD/barril. **Proxy de commodities preferido.** |
| `copper` | Cobre | `commodity_prices` (COPPER) | **Mensual interp.** | ↑ = ciclo/crecimiento | Valores planos entre meses (ffill). "Dr. Copper". |

⚠️ **Hueco de datos:** `commodity_prices` **no contiene GOLD ni SILVER** (el pipeline
`commodity_prices` no los cargó pese a estar en su config; revisar la rama FX de Alpha Vantage).

## Otras series en la DB (aún no cableadas al motor de análisis)

Disponibles pero de momento fuera del `analysis`; se integrarán cuando el estudio las
necesite.

| Dominio | Tabla(s) | Frecuencia | Notas para el estudio |
|---|---|---|---|
| Repo tri-party (NY Fed) | `repo_operations`, `gcf_*`, `repo_market_split` | Diaria | Volúmenes/colateral. Relevante para liquidez de financiación (funding). |
| **Repo USA — OFR** (DVP/GCF/tri-party) | `ofr_repo_series` | **Diaria (2018–)** | Tasa (AR, %), volumen negociado (TV) y vivo (OV) por venue y tenor. **DVP = canal bilateral compensado de hedge funds.** Ver bloque dedicado abajo. Pendiente de cablear al motor `analysis`. |
| BCE mercado monetario | `ecb_market_indicators`, `ecb_rates`, `ecb_balance_sheet` | Mensual | Liquidez EUR; útil para "liquidez global". |
| COT (CFTC) | `cot_reports` | Semanal (viernes) | Posicionamiento de traders por commodity, no liquidez per se. |
| Precios commodities | `commodity_prices` | Semanal/mensual | WTI, oro, cobre… (sensibles a liquidez/dólar). |
| Subastas Tesoro | `treasury_auctions` | Diaria | Emisión; drena/aporta según se combine con TGA. |

---

## Liquidez neta — ✅ implementada (2026-07-07)

El proxy estándar de **liquidez neta** es:

> **Liquidez neta ≈ Balance total Fed (WALCL) − TGA − Reverse Repo (RRP)**

Las tres piezas ya se descargan (pipeline `liquidity`, tabla `liquidity_series`) y están
**todas normalizadas a millones USD**, de modo que la resta es directa. La serie derivada
`net_liquidity` del motor `analysis` las alinea a semanal y las combina.

⚠️ **Trampa de unidades (resuelta en el pipeline):** FRED entrega `WALCL` y `WTREGEN` en
millones, pero `RRPONTSYD` en **miles de millones**. El pipeline multiplica el RRP ×1000 al
cargar. Todo en `liquidity_series` está ya en millones USD; no volver a convertir.

**Refinamiento posible:** existen variantes diarias (`WDTGAL` para la TGA) si se quisiera
liquidez neta a frecuencia diaria en lugar de semanal.

---

## Repo USA — OFR (U.S. Repo Markets Data Release) — ✅ implementada (2026-07-08)

Pipeline `ofr_repo`, tabla `ofr_repo_series` (formato largo). Fuente: **Office of Financial
Research** (Tesoro EE. UU.), Short-Term Funding Monitor. API REST pública sin API key
(`https://data.financialresearch.gov/v1/series/timeseries/?mnemonic=<X>`). **Diaria, 2018–hoy.**

Cubre los tres *venues* del repo garantizado de EE. UU. — la dimensión **tasa + tenor por
venue** que la fuente NY Fed (`repo_operations`) NO da. Son complementarias: NY Fed da
*composición de colateral y haircut*; OFR da *tasa, volumen y plazo por canal*.

**Venues (columna `venue`):**
- `DVP` — Delivery-versus-Payment: bilateral **compensado** vía FICC. El prestatario elige el
  título concreto → **canal de apalancamiento de los hedge funds** (basis trade del Tesoro).
  El de mayor volumen (~$3 billones/día negociado, ~$3,7 B vivo).
- `GCF` — General Collateral Finance: mercado **interdealer** de colateral general (~$245 MM).
- `TRI` — tri-party: se negocia contra **clases** de colateral (~$2,3 billones).

**Métricas (columna `metric`) y unidades (ya normalizadas por el pipeline):**
- `AR` = tasa media ponderada → **porcentaje** (`unit='percent'`).
- `TV` = volumen negociado (flujo diario de repo nuevo) → **millones USD** (`unit='millions USD'`).
- `OV` = volumen vivo (saldo pendiente) → **millones USD**. Solo `DVP` y `GCF` (tri-party no lo da).

**Segmentos de tenor (columna `segment`):** `TOT` (total), `OO` (overnight & open),
`LE30` (≤30 días), `G30` (>30 días). El catálogo cargado es curado (16 series headline);
la API tiene ~160 mnemónicos (más buckets de colateral) ampliables si el estudio lo pide.

⚠️ **Trampas:**
- **Unidades:** la API entrega los volúmenes en **dólares en bruto**; el pipeline los pasa a
  **millones USD** (÷1e6) para homogeneizar con `liquidity_series` etc. No volver a convertir.
- **Vintage preliminar:** se descarga la versión `-P` (llega hasta ayer); la OFR la revisa a
  final con rezago. El UPSERT reescribe el valor si cambia → los últimos días pueden moverse.
- **Señal esperada:** la tasa DVP y sus **picos** (no el nivel medio) marcan escasez de
  garantía/reservas → variable **episódica/umbral**, como `funding_stress`. El *volumen vivo*
  DVP aproxima el apalancamiento acumulado (relevante para riesgo de desapalancamiento).

---

## Tasas repo y estrés — OFR / FNYR (tabla `ofr_reference_rates`) — ✅ implementada (2026-07-08)

Pipeline `ofr_rates`, dataset **FNYR** de la OFR (misma API pública sin key). **Diario 2018-04–hoy.**
Descompone el mnemónico en `rate` (familia) y `stat` (estadístico).

**Tasas (`rate`):** `SOFR`, `BGCR` (Broad GC), `TGCR` (Tri-party GC) — repo garantizado; más
`EFFR`, `OBFR` (no garantizado, solo nivel, para spreads tipo SOFR−EFFR).

**Estadístico (`stat`) y unidad (normalizada):**
- `LEVEL`, `P1`, `P25`, `P75`, `P99` → **porcentaje**. La tasa publicada es la mediana; los
  percentiles describen la distribución intradía de operaciones.
- `VOLUME` → **millones USD** (la API lo da en dólares brutos → ÷1e6).

**La señal clave — cola P99:** `P99 − LEVEL` (en puntos básicos) aísla el estrés. Máximo
histórico **17-sep-2019, SOFR P99 = 9,00%** (crisis repo). Es una variable **episódica/umbral**
como `funding_stress`: la información está en los **picos**, no en el nivel medio → analizar por
eventos/umbral, no por correlación lineal. Complementa a `ofr_repo_series` (volúmenes por venue)
y a `funding_rates` (SOFR−EFFR). Pendiente de cablear al motor `analysis`.
