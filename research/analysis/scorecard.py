# research/analysis/scorecard.py
# Scorecard de señales: mide el poder ADELANTADO de cada serie sobre los
# retornos FUTUROS de un activo, a varios horizontes, de forma realista
# (alineando por fecha de publicación) y comprobando estabilidad por subperiodos.
#
# Convención de signo (ver methodology.md §3-4): las correlaciones se devuelven
# "alineadas" = corr × dirección_de_la_serie, de modo que un valor POSITIVO
# significa "el factor se movió en el sentido que, según la hipótesis, apoya al
# activo, y ADELANTÓ al movimiento". Negativo = relación contraria a la esperada.

from __future__ import annotations

import pandas as pd

from .series import build_weekly_frame, series_meta, transform_for
from .correlation import to_changes

DEFAULT_HORIZONS = (1, 4, 13, 26)  # semanas


def forward_return(price: pd.Series, horizon: int) -> pd.Series:
    """Retorno futuro del activo en `horizon` semanas: P(t+h)/P(t) − 1."""
    return price.shift(-horizon) / price - 1.0


def _prepare_predictor(frame: pd.DataFrame, predictor: str) -> pd.Series:
    """Transforma el predictor y lo desplaza por su retardo de publicación."""
    pred = to_changes(frame[predictor], transform_for(predictor))
    lag = int(series_meta(predictor, "publish_lag_weeks", 0) or 0)
    if lag:
        # El valor con fecha t solo se conoce en t+lag → desplazar hacia delante.
        pred = pred.shift(lag)
    return pred


def scan(
    predictors: list[str],
    target: str,
    horizons=DEFAULT_HORIZONS,
    subsample_split: str = "2020-01-01",
    min_overlap: int = 40,
    ref_horizon: int = 13,
) -> pd.DataFrame:
    """
    Para cada predictor, correlación (alineada por dirección) de su cambio con el
    retorno futuro de `target` a cada horizonte, sobre toda la muestra.

    Añade columnas de estabilidad: signo de la correlación al `ref_horizon` en
    cada subperiodo (antes/después de `subsample_split`) y si coinciden.

    Returns: DataFrame indexado por predictor.
    """
    split = pd.Timestamp(subsample_split)
    rows = []

    for p in predictors:
        frame = build_weekly_frame([p, target])
        if frame.empty or frame.shape[0] < min_overlap:
            rows.append({"predictor": p, "n": 0})
            continue

        pred = _prepare_predictor(frame, p)
        direction = int(series_meta(p, "direction", 1) or 1)
        rec = {"predictor": p, "n": int(frame.shape[0])}

        def aligned_corr(pred_s, price_s, h):
            fr = forward_return(price_s, h)
            pair = pd.concat([pred_s, fr], axis=1).dropna()
            if len(pair) < min_overlap:
                return float("nan")
            return pair.iloc[:, 0].corr(pair.iloc[:, 1]) * direction

        # Correlación a cada horizonte (muestra completa)
        for h in horizons:
            rec[f"{h}w"] = aligned_corr(pred, frame[target], h)

        # Estabilidad: mismo signo al ref_horizon antes/después del corte
        pre_mask = frame.index < split
        c_pre = aligned_corr(pred[pre_mask], frame[target][pre_mask], ref_horizon)
        c_post = aligned_corr(pred[~pre_mask], frame[target][~pre_mask], ref_horizon)
        rec[f"pre_{ref_horizon}w"] = c_pre
        rec[f"post_{ref_horizon}w"] = c_post
        rec["estable"] = (
            pd.notna(c_pre) and pd.notna(c_post)
            and (c_pre > 0) == (c_post > 0)
            and abs(c_pre) > 0.05 and abs(c_post) > 0.05
        )
        rows.append(rec)

    df = pd.DataFrame(rows).set_index("predictor")
    # Ordenar por |correlación| al horizonte de referencia (descendente)
    if f"{ref_horizon}w" in df.columns:
        df = df.reindex(df[f"{ref_horizon}w"].abs().sort_values(ascending=False).index)
    return df.round(3)
