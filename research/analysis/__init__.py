# research/analysis — motor reutilizable del estudio liquidez↔bolsa.
#
# Uso típico:
#   from research.analysis import build_weekly_frame, lead_lag, to_changes
#   df = build_weekly_frame(["sp500", "fed_soma", "nfci"])
#   corr = lead_lag(to_changes(df["fed_soma"], "diff"),
#                   to_changes(df["sp500"], "pct_change"), max_lag=26)

from .series import (
    SERIES,
    available,
    load_series,
    build_weekly_frame,
    series_meta,
    transform_for,
)
from .correlation import (
    to_changes,
    lead_lag,
    best_lag,
    rolling_corr,
)
from .scorecard import (
    scan,
    forward_return,
    DEFAULT_HORIZONS,
)
from .backtest import run_strategy, run_riskoff

__all__ = [
    "SERIES", "available", "load_series", "build_weekly_frame",
    "series_meta", "transform_for",
    "to_changes", "lead_lag", "best_lag", "rolling_corr",
    "scan", "forward_return", "DEFAULT_HORIZONS",
    "run_strategy", "run_riskoff",
]
