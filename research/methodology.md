# Metodología del estudio liquidez↔bolsa

Convenciones **fijas**. Si cambia alguna, se actualiza aquí con la fecha y el motivo, para
que los resultados entre sesiones sean comparables.

## 1. Frecuencia común: semanal (viernes, `W-FRI`)

- Todo se alinea a una rejilla semanal terminada en viernes (`W-FRI`), coherente con la
  convención ya usada en el proyecto (COT y commodities).
- **Resampleo:** se toma el **último valor** de la semana (`.last()`) para niveles/precios.
  Series de baja frecuencia (semanales publicadas otro día) se reindexan a la rejilla y se
  **propagan hacia delante** (`ffill`) hasta el siguiente dato real.
- Motivo: mezclar diario (bolsa) con semanal (Fed, NFCI) exige un denominador común; semanal
  es el mínimo común que no inventa datos intra-semana de las series lentas.

## 2. Estacionariedad: correlacionar **cambios**, no niveles

- Los niveles (S&P, balance Fed) tienen tendencia; correlacionar niveles con niveles infla
  la correlación de forma espuria.
- **Convención por defecto:**
  - Precios (`sp500`, `btc`): **rendimiento porcentual** semanal (`pct_change`).
  - Balance Fed / liquidez (`fed_*`): **variación** semanal (`diff`) — el flujo (Δ liquidez)
    es lo que mueve el mercado, más que el nivel.
  - NFCI: es ya un índice estacionario (media 0); se puede usar en **nivel** o en `diff`.
    Documentar cuál se usa en cada prueba.
- Cuando se estudien niveles a propósito (p. ej. cointegración), se dirá explícitamente.

## 3. Signo del lead/lag (convención crítica)

`analysis.correlation.lead_lag(x, y, max_lag)` calcula `corr(x.shift(k), y)` para cada `k`:

- **`k > 0` → `x` ADELANTA a `y` por `k` semanas** (el valor de `x` de hace `k` semanas se
  correlaciona con `y` de hoy). Es lo que buscamos: ¿la liquidez adelanta a la bolsa?
- `k < 0` → `y` adelanta a `x`.
- `k = 0` → correlación contemporánea.

Por tanto, en `lead_lag(liquidez, bolsa)`, un **pico en k>0** significa que la liquidez es
un **indicador adelantado** del mercado, con retardo = `k` semanas.

## 4. Signo/dirección de las series

- Antes de interpretar, aplicar la columna **dirección** del `data_dictionary.md`.
- **NFCI va invertido** (más alto = menos liquidez). Al correlacionar con la bolsa se espera
  signo negativo; para leerlo como "liquidez" se puede usar `-nfci`.

## 5. Ventana y submuestras

- Cuidado con regímenes: el vínculo liquidez↔bolsa cambió tras 2008 (QE) y 2020 (COVID).
  Reportar el periodo de cada prueba y, cuando importe, partir en submuestras
  (p. ej. 2009–2019 vs 2020–hoy).

## 6. Registrar todo

Cada prueba va al `research_log.md` con: hipótesis, series y transformaciones, periodo,
resultado (correlación, mejor lag) y conclusión — **incluidos los resultados nulos**.

---

### Historial de cambios de convención

- **2026-07-07** — Convenciones iniciales establecidas (frecuencia W-FRI, cambios vs niveles,
  signo lead/lag). Motivo: arranque del estudio.
