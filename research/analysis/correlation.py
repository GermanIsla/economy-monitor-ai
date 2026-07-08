# research/analysis/correlation.py
# Primitivas de correlación lead/lag para el estudio liquidez↔bolsa.
#
# Convención de signo (ver research/methodology.md §3):
#   lead_lag(x, y)[k]  con  k > 0  =>  x ADELANTA a y por k periodos.

from __future__ import annotations

import pandas as pd


def to_changes(s: pd.Series, method: str = "pct_change") -> pd.Series:
    """
    Transforma una serie a cambios para trabajar en régimen estacionario.

    method:
        'pct_change' → rendimiento relativo (por defecto para precios).
        'diff'       → variación absoluta (por defecto para niveles de liquidez).
        'level'      → sin transformar (para índices ya estacionarios, p. ej. NFCI).
    """
    if method == "pct_change":
        return s.pct_change()
    if method == "diff":
        return s.diff()
    if method == "level":
        return s
    raise ValueError(f"method desconocido: {method!r}")


def lead_lag(
    x: pd.Series,
    y: pd.Series,
    max_lag: int = 26,
    min_overlap: int = 20,
) -> pd.Series:
    """
    Correlación de x contra y desplazando x en el rango [-max_lag, +max_lag].

    Para cada k se calcula corr(x.shift(k), y): con k>0, los valores pasados de x
    se alinean con el presente de y, de modo que **k>0 significa que x adelanta a y**.

    Args:
        x, y:     series alineadas al mismo índice (usa build_weekly_frame antes).
        max_lag:  desplazamiento máximo en periodos (semanas si la rejilla es W-FRI).
        min_overlap: nº mínimo de pares solapados para calcular una correlación;
                     por debajo se devuelve NaN (evita correlaciones de pocos puntos).

    Returns:
        pd.Series indexada por lag (int), con la correlación de Pearson en cada lag.
    """
    joined = pd.concat([x.rename("x"), y.rename("y")], axis=1).dropna()
    if joined.empty:
        return pd.Series(dtype="float64", name="corr")

    out = {}
    for k in range(-max_lag, max_lag + 1):
        shifted = joined["x"].shift(k)
        pair = pd.concat([shifted, joined["y"]], axis=1).dropna()
        if len(pair) < min_overlap:
            out[k] = float("nan")
        else:
            out[k] = pair.iloc[:, 0].corr(pair.iloc[:, 1])

    res = pd.Series(out, name="corr")
    res.index.name = "lag"
    return res


def rolling_corr(x: pd.Series, y: pd.Series, window: int = 52,
                 min_periods: int | None = None) -> pd.Series:
    """
    Correlación móvil entre x e y sobre una ventana deslizante (semanas).

    Sirve para ver cómo cambia la relación a lo largo del TIEMPO de calendario
    (regímenes): tramos donde dos series están muy acopladas y otros donde no.
    """
    j = pd.concat([x.rename("x"), y.rename("y")], axis=1).dropna()
    if j.empty:
        return pd.Series(dtype="float64")
    mp = min_periods if min_periods is not None else max(window // 2, 10)
    return j["x"].rolling(window, min_periods=mp).corr(j["y"])


def best_lag(corr: pd.Series) -> dict:
    """
    Devuelve el lag de mayor correlación en valor absoluto.

    Returns dict: {lag, corr, abs_corr}. Un lag>0 indica que la primera serie
    (x en lead_lag) adelanta a la segunda por ese nº de periodos.
    """
    c = corr.dropna()
    if c.empty:
        return {"lag": None, "corr": float("nan"), "abs_corr": float("nan")}
    k = c.abs().idxmax()
    return {"lag": int(k), "corr": float(c.loc[k]), "abs_corr": float(abs(c.loc[k]))}
