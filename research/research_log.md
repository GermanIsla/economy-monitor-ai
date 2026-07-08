# Bitácora de investigación — liquidez↔bolsa

Registro cronológico (más reciente arriba). Cada entrada: **hipótesis · datos · método ·
resultado · conclusión/siguiente paso**. Se registran también los resultados nulos.

---

## 2026-07-08 — Libro repo de primary dealers (NYPD) + consolidación de páginas de repo

**Contexto.** Tercera fuente OFR del día: financiación repo de los **primary dealers**
(FR2004 / dataset NYPD). Pipeline `ofr_dealer`, tabla `ofr_dealer_financing`.

**Qué es.** El libro repo real de los dealers: `RP` (repo, securities out) y `RRP` (reverse
repo, securities in) por colateral y tenor, semanal. Es el "repo bilateral" más cercano al
**NCCBR** (no descargable): ~60% del reverse repo de dealers es bilateral sin compensar.
Captura la crisis repo de sep-2019 (repo total pico **$2,64 billones**).

**Trampa resuelta.** En NYPD, `AFtD`/`AFtR` (que probé primero) resultaron ser **fails**
(fallos de entrega, máx ~$500B), NO financiación. La financiación real es `RP`/`RRP` (~$2,6 B).
Se rehízo el modelo. Además `RP`/`RRP` **se discontinúan en 2021**: tras la revisión FR2004-2022
la financiación de dealers pasó al formato por venue, ya cubierto en `ofr_repo_series`. Es el
patrón "datos recientes vs antiguos" que anticipaba el usuario.

**Consolidación de dashboard.** Las tres fuentes OFR se unifican en una sola página
**`/repo-bilateral`** con pestañas (Volúmenes por venue · Tasas y estrés · Primary dealers),
eliminando `/ofr-repo` y `/ofr-rates`. El tri-party NY Fed (colateral/haircut) sigue en `/repo`.

## 2026-07-08 — Tasas repo con percentiles y volumen: OFR/FNYR (estrés de financiación)

**Contexto.** Segunda incorporación del día desde la API OFR: dataset **FNYR** (tasas de
referencia NY Fed). Pipeline `ofr_rates`, tabla `ofr_reference_rates`, página `/ofr-rates`.
Cierra el backlog *"volumen de SOFR y percentil 99"*.

**Qué añade.** SOFR, BGCR, TGCR (repo garantizado) con **percentiles 1/25/75/99 y volumen**,
diario 2018–hoy (41.364 filas). Lo valioso son los **percentiles**: la tasa publicada es la
mediana; el **P99** recoge las operaciones más caras del día → cuando se dispara sobre el nivel,
hay escasez de garantía. La derivada **P99 − nivel** (pb) aísla el estrés.

**Validación de datos.** El máximo histórico de SOFR P99 es **17-sep-2019 = 9,00%** (la crisis
repo que forzó la reintervención de la Fed), seguido de cierres de trimestre y marzo-2020. Los
datos capturan correctamente los episodios conocidos.

**NCCBR descartado como fuente.** El repo bilateral **sin compensar** (NCCBR) NO es descargable
por la API pública de la OFR (nivel-transacción, confidencial). El sustituto más cercano es el
libro *reverse repo* de los **primary dealers** (dataset `NYPD`, 194 series, misma API) →
anotado como siguiente candidato en el backlog.

**Reutilización.** Se extrajo `add_sp500_reference(fig, periodo_dias)` a
`dashboard/components/charts.py`: superpone el S&P 500 en eje secundario (toggle por leyenda) en
cualquier gráfico. Aplicado ya a `/ofr-repo` y `/ofr-rates`.

**Sin análisis todavía** — montaje y visualización. Siguiente: cablear al motor `analysis` la
cola P99 (umbral) junto con la tasa/saldo DVP de `ofr_repo`.

## 2026-07-08 — Datos de repo bilateral cableados: OFR (DVP/GCF/tri-party)

**Contexto.** Se incorpora la **capa 2 de repo** que faltaba: el U.S. Repo Markets Data
Release de la **OFR** (Office of Financial Research, Tesoro EE.UU.), vía su API pública sin
key. Pipeline `ofr_repo`, tabla `ofr_repo_series` (formato largo), página `/ofr-repo`.

**Qué añade frente a lo que ya había.** La fuente NY Fed (`repo_operations`) daba
*composición de colateral y haircut* de **tri-party**. La OFR añade la dimensión que faltaba:
**tasa, volumen negociado y volumen vivo por venue y tenor**, e incluye el venue **DVP**
(bilateral compensado vía FICC) entero — el canal por el que los hedge funds montan
apalancamiento (basis trade del Tesoro). Complementarias, no redundantes.

**Datos cargados.** 16 series headline (curadas de ~160 mnemónicos), **diarias 2018–hoy**
(28.683 filas). Venues: `DVP`, `GCF`, `TRI`. Métricas: `AR` (tasa %, ponderada), `TV`
(volumen negociado, millones USD), `OV` (saldo vivo, solo DVP/GCF). Tenores: `TOT`, `OO`
(overnight&open), `LE30`, `G30`. Volúmenes normalizados a millones USD (la API los da en
dólares en bruto). Vintage preliminar `-P` (se revisa; UPSERT reescribe).

**Foto actual (2026-07-06).** DVP negocia ~**$3,01 billones/día** (saldo vivo ~$3,68 B),
tri-party ~**$2,33 billones**, GCF ~**$245.000 millones**. Tasa DVP total ~3,6%.

**Sin análisis todavía** — solo montaje y visualización, como pidió el usuario ("montar todos
primero, estudiar después"). **Siguiente paso propuesto:** cablear al motor `analysis` la
**tasa DVP** (variable episódica/umbral, como `funding_stress` — mirar picos, no nivel medio)
y el **saldo vivo DVP** (proxy de apalancamiento acumulado → riesgo de desapalancamiento).
Historia corta (2018+) y solapada; tratar como señal de régimen/estrés, no de timing fino.

## 2026-07-07 — Estrategia risk-off vs B&H (bloque G, cierre del día)

**Giro de enfoque:** en vez de "largo solo cuando la señal es favorable" (se pierde la subida),
**largo SALVO en regímenes de riesgo alto** (VIX o crédito en su 15% superior → liquidez).
Función `run_riskoff` + bloque G en la página (curva estrategia vs B&H + métricas). Umbral con
ventana expansiva; sin costes aún.

**Resultado clave (S&P, VIX+crédito, q=0.85, 1990+):** **bate a comprar-y-mantener en retorno
ajustado al riesgo** — Sharpe **0,65 vs 0,59** y caída máxima **−29% vs −56%**, invertido ~68%
del tiempo. CAGR +6,4% vs +8,8% (menor en absoluto, pero con mayor Sharpe el hueco se cierra
con **apalancamiento** → siguiente fase). BTC: la de-risk reduce algo el drawdown pero apenas
mejora (sus caídas no siempre las precede el VIX de renta variable).

**Objetivo confirmado con el usuario:** batir a comprar-y-mantener (no solo gestionar riesgo).
Vamos por buen camino: primer resultado que supera al B&H en Sharpe. **Próximos pasos:** (1)
apalancar la versión de mayor Sharpe para batir en absoluto; (2) walk-forward + costes; (3) más
datos (OFR repo bilateral, del backlog) para dar muestra al crédito→BTC.

## 2026-07-07 — Backtest de validación: ¿aportan edge las señales?

**Herramienta** `research/analysis/backtest.py` (`run_strategy`): largo solo cuando la señal es
favorable, umbral con **ventana expansiva** (anti-look-ahead), sin costes. Métricas + edge =
retorno medio semanal cuando invertido − media general. Parámetro `hold` (semanas de tenencia).

**Resultados (hold 13s):**
- **Controles limpios → el marco NO es espurio:** crédito no ayuda al S&P (edge −0,08%); VIX
  no ayuda a BTC — es **fuertemente NEGATIVO** (edge −0,70%/sem). Cada señal actúa donde debe.
- **VIX alto → S&P:** edge pequeño y positivo (+0,05%/sem). Real pero modesto.
- **Crédito alto → BTC:** edge **+1,07%/sem**, el mayor — pero solo 6% de las semanas (muestra
  pequeña, cautela).
- **Ningún overlay de timing bate a comprar-y-mantener** (estar fuera del mercado se pierde la
  tendencia alcista: p. ej. VIX→S&P cagr +4,8% vs B&H +8,8%).

**Veredicto (responde a la pregunta del usuario "¿ayudan de verdad los datos?"):** SÍ, pero
**modestamente y sobre todo para GESTIÓN DE RIESGO, no para timing que bata al B&H**. Lo más
robusto y consistente es una regla **risk-off para BTC**: con VIX / estrés de crédito / estrés
de financiación / haircuts elevados, BTC rinde peor (edge −0,70% del control VIX→BTC lo
confirma). Correlaciones de 0,1-0,2 → edges pequeños; el crédito→BTC destaca pero con poca
muestra. Sin magia, pero direccionalmente válido.

## 2026-07-07 — Repo por calidad de colateral (nulo) + asimetría de estrés S&P/BTC

**Repo por calidad de colateral (petición del usuario: ¿sube el bueno o el malo?).** Estudiada
la corr de Δvolumen de colateral ALTA (Tesoro/Agencia/MM) vs BAJA (Equity/Corp/ABS/CDO) calidad,
y por tipo individual, vs retorno futuro. **Resultado ~0 en todo** (|corr|<0,18, sin patrón).
Los *volúmenes* de repo por calidad no predicen la bolsa; el único con señal es el `repo_haircut`.
Anotado en `data_backlog.md` como estudiado-descartado.

**Asimetría del estrés de financiación S&P vs BTC (observación del usuario, CONFIRMADA).**
Tras estrés alto (p90 de SOFR−EFFR):
- **S&P: retorno futuro MEJOR** que la media (+1,64% vs +1,09% a 4s; +4,36% vs +3,45% a 13s) →
  contrarian, suelo de compra.
- **BTC: retorno futuro PEOR** (+2,45% vs +3,63% a 4s; **+5,40% vs +14,94% a 13s**) → el estrés
  es anticipatorio de peor comportamiento.
- Mecanismo (usuario): el estrés hace que la banca reduzca riesgo semanas → el activo de más
  beta (BTC) sigue penalizado; el S&P (más seguro) rebota. **Misma señal, regla opuesta por
  activo.** Visible en el bloque F cambiando de activo.

**Backlog de datos futuros creado:** `research/data_backlog.md` (OFR repo bilateral/patrocinado,
NCCBR, SOFR vol/p99, NFCI vintage, arreglo GOLD/SILVER, etc.).

## 2026-07-07 — Exprimir el repo tri-party: haircuts de colateral de riesgo

**Objetivo del usuario:** sacar valor de los datos que ya tenemos (repo tri-party, mensual)
antes de descargar nuevos. Exploradas: márgenes/haircuts (varían), concentración top-3 (vacía),
split overnight/term (vacío/plano) → el único con señal es el **haircut**.

**Serie nueva `repo_haircut`** = margin_median medio del colateral de riesgo (Equities,
Corporates Non-IG, ABS Non-IG, CDOs, CMO PL Non-IG). Mecanismo del usuario: haircut alto =
menos apalancamiento posible = desapalancamiento/estrés.

**Resultado:** **S&P sin señal (~0)**; **BTC negativo persistente**: nivel haircut vs retorno
futuro 3m = **−0,19 (full), −0,24 (post-2020)**, contemporáneo −0,17. Coherente: BTC es el
activo más sensible al apalancamiento. Correlación negativa = útil (invertir: haircut ↑ →
reducir BTC). Añadido al scorecard de la página (dir −1). Haircut de riesgo **en máximos ahora**
(9,0-9,5 en 2024-25) → apalancamiento tensándose, junto con el repunte del SOFR−EFFR.

## 2026-07-07 — Liquidez de financiación (SOFR): pipeline + primer análisis

**Datos.** Pipeline `funding` (tabla `funding_rates`): SOFR (2018+), EFFR (2014+), IORB (2021+).
Motor: `sofr`, `funding_stress` (=SOFR−EFFR). Es la **capa 2** (liquidez de financiación), el
foco principal del usuario.

**La serie funciona:** capta el **pico de repo de sep-2019** (SOFR 2,95% sobre EFFR; pico
semanal 0,69) y muestra **tensión reciente en oct-nov 2025 (0,14–0,20)** — coherente con reservas
haciéndose escasas tras vaciarse el RRP + QT. **Señal viva a vigilar.**

**Pero la correlación lineal con la bolsa ≈ 0** (S&P +0,01/+0,06; BTC ~0). **Lección de método:**
`funding_stress` es una variable **episódica/umbral** (casi siempre ~0, picos raros). La
correlación lineal la promedia y la diluye; la señal está en los **eventos/umbrales**, no en el
nivel medio. → Siguiente análisis correcto: **estudio de eventos** (qué hace la bolsa cuando el
estrés supera un umbral), no correlación lineal. No integrado aún en la página por eso.

**Estudio de eventos (bloque F de la página, umbral p90 de SOFR−EFFR):**
- **Contemporáneo:** en semanas de estrés alto el S&P cae en media **−0,27%** vs **+0,28%**
  general → confirma el mecanismo del usuario (banca vende activos para proteger reservas).
- **Forward:** tras el estrés, retorno **ligeramente superior** a la media (+1,64% vs +1,09%
  a 4s; +4,36% vs +3,45% a 13s) → los picos marcan capitulaciones (rebote), familia contrarian
  como VIX/crédito. **Cautela: ~12 episodios (2018+), autocorrelados.** Útil como señal de
  cobertura contemporánea más que de timing forward. Correlación negativa = útil igual (se invierte).

## 2026-07-07 — Métricas mejoradas (2a): reservas + señales de precio, fed_soma jubilado

**Motivación (críticas del usuario, válidas).** (1) `fed_soma` no es liquidez (es un stock/
driver); la liquidez "cantidad" son las **reservas**. (2) El **NFCI se revisa** a posteriori →
sesgo look-ahead; preferir señales **de precio** (no se revisan). Ver [[maintain-research-space]]
y `research/economic_notes.md`.

**Datos nuevos.** Pipeline `signals` (tabla `market_signals`): `BAA10Y` (crédito), `T10Y2Y`
(curva), `VIXCLS` (VIX), 1990–. Reservas `WRESBAL` añadidas a `liquidity` (~$2,97B). Motor:
`reserves`, `credit`, `curve`, `vix`. **Trampas resueltas:** WRESBAL viene en millones (factor
1.0, no 1000); el HY OAS de ICE (`BAMLH0A0HYM2`) solo llega a 2023 en FRED por licencia → se
usa `BAA10Y`.

**Scorecard v2 (corr alineada, S&P):**
- `nfci` sigue 1º (0,21 @4-13s, estable) **pero en cuarentena por sesgo de revisión.**
- **`vix` (nivel) = mejor señal HONESTA** (no se revisa): 0,05→0,15 subiendo con el horizonte,
  **estable**, y muy fuerte post-2020 (0,37). Efecto prima de riesgo (VIX alto → retorno futuro +).
- `reserves` ≈ `net_liquidity`: dependientes de régimen (positivas post-2020 ~0,16, no estables).
- `credit`/`curve` en cambios: débiles/inestables → **probar en nivel** (marco prima de riesgo).
**BTC:** nfci domina (sesgado); resto débil, muestra corta.

**v3 — refinamiento nivel/prima de riesgo (credit pasa a level, dir +1):**
- `credit` NIVEL: full ~0 pero **post-2020 +0,34 (13s) / +0,39 (26s)** en S&P. Y en **BTC es
  LA mejor señal**: +0,17 (13s), **+0,26 (26s)**, post +0,27. Spreads anchos → retorno futuro
  alto (contrarian, como el VIX). `vix`/`credit` en cambios = ruido; en **nivel** funcionan.
- `curve`: floja en ambas versiones → su señal (recesión) vive a horizonte **largo (52s+)**,
  pendiente de añadir ese horizonte.
- **Tema emergente: dos familias de señales honestas** — (1) **contrarian/prima de riesgo**
  (VIX nivel, crédito nivel): "comprar cuando hay estrés", fuertes post-2020; (2)
  **liquidez-cantidad** (reservas, liquidez neta): débiles y dependientes de régimen. El VIX
  manda en S&P; el crédito manda en BTC (activo de más beta) — encaja con la idea del usuario
  de que BTC es más sensible al riesgo/liquidez, vía el canal de crédito a horizonte largo.

**Lectura.** Quitando el NFCI (sesgado), el mejor predictor honesto hoy es el **VIX en nivel**;
la liquidez-cantidad (reservas/neta) solo "funciona" en el régimen post-2020. Página `/estudio`
actualizada al panel v2 con aviso del sesgo NFCI.

**Siguiente.** (i) probar `credit`/`vix`/curve en **nivel** (prima de riesgo); (ii) NFCI vintage
(ALFRED) para cuantificar el sesgo; (iii) el gran objetivo del usuario: **spreads repo/SOFR**
(liquidez de financiación) y datos de repo bilateral/OFR.

## 2026-07-07 — Emisión neta de letras → RRP → mercado + correlación móvil

**Hipótesis del usuario (letras engrasan liquidez vía repo/RRP).** Emisión neta =
Δ del stock de letras (`bills_outstanding.diff(4)`, ~mensual).

**Resultados (era RRP activo, 2021+):**
- **Emisión neta ↔ ΔRRP: corr −0,58** (−0,36 toda la historia), **contemporánea** (mejor
  desfase k=0). → El primer eslabón de la cadena es REAL y rápido: emitir letras drena el
  RRP (los MMF cambian efectivo del RRP por letras). Fontanería confirmada.
- **Pero la cadena NO llega al mercado:** −ΔRRP vs retorno futuro 4s ≈ 0 (S&P −0,02, BTC
  +0,04); emisión neta vs retorno futuro ≈ 0 (S&P −0,09 a 4s). El drenaje **compensaba el
  QT** (colchón que estabilizó la liquidez), no fue un impulso adelantado → co-tendencia, no
  predicción. La intuición del usuario (retardo/co-tendencia) acertó.
- **Contexto forward:** el RRP pasó de $2,05B (pico 2022) a ~$2.000M hoy → **canal agotado**.
  La nueva emisión drenará reservas bancarias directamente: a vigilar como riesgo de liquidez.

**Conclusión de las 2 hipótesis del usuario:** letras (flujo, stock y neta) no dan señal
directa de timing sobre la bolsa; su valor es de **fontanería/régimen**, no de predicción.

**Añadido al visor.** Bloque D (correlación móvil 52s = "regímenes en el tiempo", responde a
la observación del usuario de que la relación tiene «épocas») y bloque E (emisión→RRP).
Herramienta nueva reutilizable: `rolling_corr` en `analysis/correlation.py`.

## 2026-07-07 — Visor en el dashboard + lección nivel-vs-cambio (letras)

**Visor.** Nueva página `dashboard/pages/estudio.py` (`/estudio`, "Estudio Liquidez") con
3 bloques: (A) scorecard, (B) letras en circulación vs mercado, (C) perfil lead/lag de NFCI
y fed_soma. Se recalcula en vivo desde el motor `research/analysis`. Selector S&P/BTC.

**Hallazgo (observación del usuario resuelta).** Serie nueva `bills_outstanding` (stock de
letras, reconstruido de subastas, ~$6,9B). El usuario notó que "se parece" a Bitcoin:
- **Correlación de NIVELES**: bills vs BTC **+0,87**, vs S&P **+0,93** (¡sí, casi calcadas!).
- **Correlación de CAMBIOS**: bills vs BTC **+0,02**, vs S&P **+0,14**.
→ El parecido es **tendencia compartida** (ambas suben con los años), no relación predictiva.
Confirma la convención de la metodología §2: correlacionar cambios, no niveles. Es el ejemplo
didáctico del estudio.

## 2026-07-07 — Primer scorecard (S&P 500 y Bitcoin) + herramienta

**Herramienta.** `research/analysis/scorecard.py`: `scan(predictors, target)` mide la corr
del cambio de cada serie con el **retorno futuro** del activo a 1/4/13/26 semanas, alineando
por **fecha de publicación** (`publish_lag_weeks`) y comprobando estabilidad en subperiodos
(corte 2020-01-01). Correlación "alineada" = corr × dirección → **+ = el factor adelantó a
favor del activo**.

**Datos.** Predictores: `nfci`, `fed_soma`, `net_liquidity`, `wti`, `bill_issuance`,
`repo_total`, `repo_risk_share`. Objetivos: `sp500`, `btc`. Semanal (W-FRI).

**Resultados (corr alineada, muestra completa):**
- **NFCI = la señal más robusta.** S&P: 0,14 (1s) → 0,21 (4-13s); BTC: ~0,13 estable en todos
  los horizontes. **Estable** en ambos subperiodos y en ambos activos. Condiciones financieras
  (invertidas) adelantan al mercado ~1-3 meses. Es el ancla del sistema.
- **fed_soma (QE/QT) = 2º**, estable, y **se refuerza post-2020** (0,23 a 13s en S&P) y a
  horizontes largos. La expansión/contracción del balance importa, sobre todo en el régimen actual.
- **net_liquidity y repo_risk_share = dependientes de régimen**: cambian de signo pre/post 2020
  (net_liquidity: −0,05 → +0,18; repo_risk_share: −0,24 → +0,16). NO estables en toda la
  historia → funcionan en la narrativa post-2020, no antes. Ojo a extrapolar.
- **Hipótesis del usuario (primer test, NO concluyente en contra):**
  - `bill_issuance` (emisión BRUTA de letras, 4s móvil): ≈ 0 a todos los horizontes. Pero
    puede ser la construcción equivocada: probar emisión **neta** (de vencimientos) y la vía
    indirecta (bills → drenaje del RRP → liquidez), no el efecto directo.
  - `repo_total` / `repo_risk_share`: débiles/inestables, y limitados por ser **mensuales**
    (191 puntos, acaban 2026-03). Mejor para régimen que para timing.
- **Cross-asset:** la hipótesis "BTC más sensible a liquidez" NO queda confirmada aquí; BTC
  responde a NFCI de forma parecida al S&P y su muestra es corta (2015+). Pendiente de más análisis.

**Calidad de datos detectada.** `commodity_prices` no tiene GOLD ni SILVER (el pipeline no los
cargó); COPPER es mensual interpolado (valores planos entre meses) → se prefiere **WTI**
(semanal, limpio). Anotado en el diccionario.

**Caveats metodológicos (importantes).** Correlaciones **in-sample**; los retornos solapados
(13s, 26s) inflan la significancia; sin corrección por multiplicidad. Magnitudes modestas
(|corr| 0,1-0,2 ≈ 1-4% de varianza) → señales de apoyo, no de precisión. El siguiente paso
serio es validación walk-forward y combinar señales por factor.

## 2026-07-07 — Liquidez neta cableada (WALCL, TGA, RRP)

**Contexto.** Nuevo pipeline `liquidity` (tabla `liquidity_series`) con `WALCL`, `WTREGEN`
(TGA) y `RRPONTSYD` (RRP) desde FRED, todo normalizado a millones USD (RRP ×1000). Añadidas
al motor las claves `walcl`, `tga`, `rrp` y la derivada `net_liquidity` (WALCL−TGA−RRP,
alineada a semanal). Datos 2003–hoy; `net_liquidity` actual ≈ $5,84 billones. Se cierra el
hueco de datos que bloqueaba el estudio.

**Sondeo preliminar (no concluyente).** `lead_lag(Δnet_liquidity, retorno_sp500)`, semanal,
2015+: correlación contemporánea ~0, máximo en **k=+3 semanas** con corr ≈ **0,13** (liquidez
adelantando a la bolsa, signo esperado pero magnitud débil). Es solo un sanity-check del
tubo; la primera hipótesis formal se planteará en la sesión de análisis.

## 2026-07-07 — Montaje del espacio de trabajo

**Contexto.** Se crea `research/` como espacio de conocimiento del estudio: diccionario de
datos, metodología, esta bitácora y el motor `analysis/`. Se añadió el pipeline `indices`
(S&P 500 + Bitcoin) como primeras variables objetivo.

**Estado de datos.** Objetivo (bolsa) cubierto: `sp500`, `btc`. Liquidez cubierta:
balance Fed (securities held outright) y NFCI. **Huecos identificados** para liquidez neta:
falta `WALCL` (balance total), `TGA` (`WTREGEN`) y `RRP` (`RRPONTSYD`) — ver diccionario.

**Sin hipótesis probadas todavía.** Siguiente paso propuesto: primera prueba exploratoria de
lead/lag entre Δ balance Fed y rendimientos del S&P (2009–hoy) usando el motor `analysis`.

<!-- Plantilla para nuevas entradas:

## AAAA-MM-DD — <título de la hipótesis>

**Hipótesis.** <qué esperamos y por qué>
**Datos.** <series (claves del diccionario) y periodo>
**Método.** <transformaciones, frecuencia, lead/lag, submuestras>
**Resultado.** <correlación, mejor lag, gráfico si aplica>
**Conclusión.** <qué concluimos / siguiente paso>
-->
