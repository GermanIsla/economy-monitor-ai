# research/analysis/backtest.py
# Backtesting SIMPLE para VALIDAR señales (no para desplegar estrategias).
# Objetivo: ¿estar largo solo cuando la señal es favorable aporta ventaja (edge)
# frente a comprar y mantener?
#
# Salvaguarda anti-look-ahead: el umbral de la señal se calcula con ventana
# EXPANSIVA (solo pasado). La posición en t usa la señal en t y gana el retorno
# de t+1. Sin costes de transacción (primer paso ilustrativo).

from __future__ import annotations

import numpy as np
import pandas as pd

from .series import build_weekly_frame, series_meta, transform_for
from .correlation import to_changes

ANN = 52  # semanas/año


def _metrics(r: pd.Series) -> dict:
    r = r.dropna()
    n = len(r)
    if n < 10:
        return {"cagr": np.nan, "sharpe": np.nan, "maxdd": np.nan, "total": np.nan}
    eq = (1 + r).cumprod()
    total = eq.iloc[-1] - 1
    cagr = eq.iloc[-1] ** (ANN / n) - 1
    sd = r.std()
    sharpe = (r.mean() * ANN) / (sd * np.sqrt(ANN)) if sd > 0 else np.nan
    maxdd = (eq / eq.cummax() - 1).min()
    return {"cagr": cagr, "sharpe": sharpe, "maxdd": maxdd, "total": total}


def run_strategy(asset: str, signal_key: str, favorable: str = "high",
                 q: float = 0.8, hold: int = 1, min_train: int = 104) -> dict:
    """
    Estrategia de validación: largo en `asset` solo cuando la señal es favorable.

    Args:
        asset:      activo objetivo (p. ej. 'sp500', 'btc').
        signal_key: serie-señal del motor.
        favorable:  'high' → largo cuando la señal supera su umbral alto;
                    'low'  → largo cuando queda por debajo de su umbral bajo.
        q:          cuantil del umbral (0.8 = quintil alto).
        hold:       semanas que se mantiene la posición tras dispararse la señal
                    (para señales contrarian que actúan a varias semanas).
        min_train:  semanas mínimas antes de operar (calienta la ventana expansiva).

    Returns dict con métricas de la estrategia y de comprar-y-mantener + curvas.
    """
    frame = build_weekly_frame([signal_key, asset])
    if frame.empty or len(frame) < min_train + 20:
        return {}

    sig = to_changes(frame[signal_key], transform_for(signal_key))
    ret = frame[asset].pct_change()

    # Umbral expansivo (solo pasado)
    if favorable == "high":
        thr = sig.expanding(min_periods=min_train).quantile(q)
        pos = (sig >= thr).astype(float)
    else:
        thr = sig.expanding(min_periods=min_train).quantile(1 - q)
        pos = (sig <= thr).astype(float)

    pos = pos.where(thr.notna())            # no operar antes de calentar
    # Mantener la posición `hold` semanas tras cada disparo de la señal
    if hold > 1:
        pos = pos.rolling(hold, min_periods=1).max()
    strat = pos.shift(1) * ret              # posición en t gana retorno en t+1

    valid = strat.notna() & ret.notna() & pos.shift(1).notna()
    strat, bh, posv = strat[valid], ret[valid], pos.shift(1)[valid]
    if len(strat) < 20:
        return {}

    m_s, m_b = _metrics(strat), _metrics(bh)
    inv = posv.mean()
    # retorno medio semanal cuando invertido vs media general (el test de edge)
    r_on = ret[valid][posv == 1].mean()
    r_all = bh.mean()

    return {
        "asset": asset, "signal": signal_key, "favorable": favorable, "q": q,
        "n": int(len(strat)), "pct_invested": inv,
        "wk_ret_on": r_on, "wk_ret_all": r_all,
        "strat": m_s, "bh": m_b,
        "eq_strat": (1 + strat).cumprod(), "eq_bh": (1 + bh).cumprod(),
        "pos": posv,
    }


def run_riskoff(asset: str, risk_keys=("vix", "credit"),
                q: float = 0.85, min_train: int = 104) -> dict:
    """
    Estrategia risk-off: largo en `asset` SALVO cuando alguna señal de riesgo
    supera su cuantil alto (ventana expansiva) → a liquidez. La idea es esquivar
    los regímenes malos manteniéndose invertido la mayor parte del tiempo, para
    batir a comprar-y-mantener en retorno ajustado al riesgo.
    """
    frame = build_weekly_frame([*risk_keys, asset])
    if frame.empty or len(frame) < min_train + 20:
        return {}

    ret = frame[asset].pct_change()
    off = pd.Series(False, index=frame.index)
    warm = pd.Series(True, index=frame.index)
    for rk in risk_keys:
        s = to_changes(frame[rk], transform_for(rk))
        thr = s.expanding(min_periods=min_train).quantile(q)
        off = off | (s >= thr)
        warm = warm & thr.notna()

    pos = (~off).astype(float).where(warm)
    strat = pos.shift(1) * ret
    v = strat.notna() & ret.notna() & pos.shift(1).notna()
    strat, bh = strat[v], ret[v]
    if len(strat) < 20:
        return {}

    return {
        "asset": asset, "risk_keys": list(risk_keys), "q": q,
        "n": int(len(strat)), "pct_invested": float(pos[v].mean()),
        "strat": _metrics(strat), "bh": _metrics(bh),
        "eq_strat": (1 + strat).cumprod(), "eq_bh": (1 + bh).cumprod(),
    }
