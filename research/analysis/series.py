# research/analysis/series.py
# Carga de series desde la base de datos y alineación a una rejilla semanal común.
#
# Fuente de verdad de CÓMO se carga y alinea cada serie. El QUÉ es cada serie
# (unidad, dirección, trampas) está en research/data_dictionary.md.

from __future__ import annotations

import pandas as pd
from sqlalchemy import select

from db.engine import get_session
from db.models.indices import MarketIndex
from db.models.fed_balance import FedBalanceAsset
from db.models.nfci import NFCIReading
from db.models.liquidity import LiquiditySeries
from db.models.treasury import TreasuryAuction
from db.models.repo import RepoOperation
from db.models.commodity_price import CommodityPrice
from db.models.signals import MarketSignal
from db.models.funding import FundingRate

# Colateral de repo considerado "de riesgo" (no gobierno/agencia/cash) para
# el ratio repo_risk_share. Ver research/data_dictionary.md.
REPO_RISKY_GROUPS = [
    "Equities", "Corporates Investment Grade", "Corporates Non Investment Grade",
    "ABS Investment Grade", "ABS Non Investment Grade", "CDOs",
    "CMO Private Label Investment Grade", "CMO Private Label Non Investment Grade",
    "Whole Loans", "Municipality Debt", "International Securities", "Other",
]

# Grupos de colateral de riesgo con haircut (margin) informativo, para medir la
# capacidad de apalancamiento del sistema: haircut alto = menos apalancamiento.
REPO_HAIRCUT_GROUPS = [
    "Equities", "Corporates Non Investment Grade", "ABS Non Investment Grade",
    "CDOs", "CMO Private Label Non Investment Grade",
]

# Rejilla semanal del estudio: viernes (ver research/methodology.md §1).
WEEKLY_FREQ = "W-FRI"

# ---------------------------------------------------------------------------
# Registro de series. Cada entrada describe cómo obtener una pd.Series
# indexada por fecha. `direction` documenta el signo (ver diccionario).
#   loader: callable() -> pd.Series (índice datetime, ordenado)
# ---------------------------------------------------------------------------


def _market_close(symbol: str):
    def _loader():
        with get_session() as s:
            rows = s.execute(
                select(MarketIndex.date, MarketIndex.close_price)
                .where(MarketIndex.index_symbol == symbol)
                .order_by(MarketIndex.date)
            ).all()
        return _to_series(rows)
    return _loader


def _fed_series(series_id: str):
    def _loader():
        with get_session() as s:
            rows = s.execute(
                select(FedBalanceAsset.date, FedBalanceAsset.value)
                .where(FedBalanceAsset.series_id == series_id)
                .order_by(FedBalanceAsset.date)
            ).all()
        return _to_series(rows)
    return _loader


def _fed_soma():
    """Securities Held Outright = TREAST + FEDDT + WSHOMCB (suma por fecha)."""
    with get_session() as s:
        rows = s.execute(
            select(FedBalanceAsset.date, FedBalanceAsset.value)
            .where(FedBalanceAsset.series_id.in_(["TREAST", "FEDDT", "WSHOMCB"]))
            .order_by(FedBalanceAsset.date)
        ).all()
    if not rows:
        return pd.Series(dtype="float64")
    df = pd.DataFrame(rows, columns=["date", "value"])
    df["date"] = pd.to_datetime(df["date"])
    return df.groupby("date")["value"].sum().sort_index()


def _liquidity_series(series_id: str):
    def _loader():
        with get_session() as s:
            rows = s.execute(
                select(LiquiditySeries.date, LiquiditySeries.value)
                .where(LiquiditySeries.series_id == series_id)
                .order_by(LiquiditySeries.date)
            ).all()
        return _to_series(rows)
    return _loader


def _weekly(s: pd.Series, freq: str = "W-FRI") -> pd.Series:
    """Resamplea a la rejilla semanal (último valor) y propaga huecos."""
    if s.empty:
        return s
    return s.resample(freq).last().ffill()


def _net_liquidity():
    """
    Liquidez neta ≈ WALCL − TGA − RRP (todo en millones USD).

    Los tres componentes tienen frecuencias distintas (WALCL/TGA semanales,
    RRP diaria), así que se alinean primero a la rejilla semanal común antes de
    combinarlos. Devuelve una serie semanal.
    """
    walcl = _weekly(_liquidity_series("WALCL")())
    tga = _weekly(_liquidity_series("WTREGEN")())
    rrp = _weekly(_liquidity_series("RRPONTSYD")())
    df = pd.concat(
        {"walcl": walcl, "tga": tga, "rrp": rrp}, axis=1
    ).ffill().dropna()
    if df.empty:
        return pd.Series(dtype="float64")
    return df["walcl"] - df["tga"] - df["rrp"]


def _bill_issuance():
    """
    Emisión bruta semanal de letras del Tesoro (security_type='Bill'), suavizada
    a suma móvil de 4 semanas para limpiar el ruido del calendario de subastas.
    """
    with get_session() as s:
        rows = s.execute(
            select(TreasuryAuction.issue_date, TreasuryAuction.total_accepted)
            .where(TreasuryAuction.security_type == "Bill")
            .order_by(TreasuryAuction.issue_date)
        ).all()
    if not rows:
        return pd.Series(dtype="float64")
    df = pd.DataFrame(rows, columns=["date", "value"])
    df["date"] = pd.to_datetime(df["date"])
    weekly = df.set_index("date")["value"].resample(WEEKLY_FREQ).sum()
    return weekly.rolling(4, min_periods=1).sum()


def _bills_outstanding():
    """
    Stock de letras del Tesoro EN CIRCULACIÓN, reconstruido de las subastas:
    +importe al emitir (issue_date), −importe al vencer (maturity_date), suma
    acumulada. Se trunca en la última fecha de emisión conocida (más allá solo
    habría vencimientos → la serie caería artificialmente hacia 0).
    """
    with get_session() as s:
        rows = s.execute(
            select(TreasuryAuction.issue_date, TreasuryAuction.maturity_date,
                   TreasuryAuction.total_accepted)
            .where(TreasuryAuction.security_type == "Bill")
        ).all()
    if not rows:
        return pd.Series(dtype="float64")
    df = pd.DataFrame(rows, columns=["issue", "mat", "amt"])
    df["issue"] = pd.to_datetime(df["issue"])
    df["mat"] = pd.to_datetime(df["mat"])
    last_issue = df["issue"].max()
    events = pd.concat([
        pd.DataFrame({"date": df["issue"], "d": df["amt"]}),
        pd.DataFrame({"date": df["mat"], "d": -df["amt"]}),
    ])
    out = (events.groupby("date")["d"].sum().sort_index().cumsum()
           .resample(WEEKLY_FREQ).last().ffill())
    return out[out.index <= last_issue]


def _repo_group(group_name: str):
    def _loader():
        with get_session() as s:
            rows = s.execute(
                select(RepoOperation.date, RepoOperation.collateral_value)
                .where(RepoOperation.group_name == group_name)
                .order_by(RepoOperation.date)
            ).all()
        return _to_series(rows)
    return _loader


def _repo_risk_share():
    """% del colateral tri-party en activos de riesgo sobre el Total (mensual)."""
    with get_session() as s:
        rows = s.execute(
            select(RepoOperation.date, RepoOperation.group_name,
                   RepoOperation.collateral_value)
            .where(RepoOperation.group_name.in_(REPO_RISKY_GROUPS + ["Total"]))
            .order_by(RepoOperation.date)
        ).all()
    if not rows:
        return pd.Series(dtype="float64")
    df = pd.DataFrame(rows, columns=["date", "group", "value"])
    df["date"] = pd.to_datetime(df["date"])
    piv = df.pivot_table(index="date", columns="group", values="value", aggfunc="sum")
    total = piv.get("Total")
    if total is None:
        return pd.Series(dtype="float64")
    risky = piv[[c for c in REPO_RISKY_GROUPS if c in piv.columns]].sum(axis=1)
    share = (risky / total).replace([float("inf"), float("-inf")], float("nan"))
    return share.dropna().sort_index()


def _repo_haircut():
    """
    Haircut (recorte de garantía) medio del colateral de riesgo en el repo tri-party.
    Proxy de la capacidad de apalancamiento: haircut alto = menos apalancamiento posible
    = estrés/desapalancamiento. Mensual.
    """
    with get_session() as s:
        rows = s.execute(
            select(RepoOperation.date, RepoOperation.group_name,
                   RepoOperation.margin_median)
            .where(RepoOperation.group_name.in_(REPO_HAIRCUT_GROUPS))
            .order_by(RepoOperation.date)
        ).all()
    if not rows:
        return pd.Series(dtype="float64")
    df = pd.DataFrame(rows, columns=["date", "g", "m"])
    df["date"] = pd.to_datetime(df["date"])
    return (df.pivot_table(index="date", columns="g", values="m")
            .mean(axis=1).dropna().sort_index())


def _commodity(series_id: str):
    def _loader():
        with get_session() as s:
            rows = s.execute(
                select(CommodityPrice.date, CommodityPrice.price)
                .where(CommodityPrice.series_id == series_id)
                .order_by(CommodityPrice.date)
            ).all()
        return _to_series(rows)
    return _loader


def _signal(series_id: str):
    def _loader():
        with get_session() as s:
            rows = s.execute(
                select(MarketSignal.date, MarketSignal.value)
                .where(MarketSignal.series_id == series_id)
                .order_by(MarketSignal.date)
            ).all()
        return _to_series(rows)
    return _loader


def _funding(series_id: str):
    def _loader():
        with get_session() as s:
            rows = s.execute(
                select(FundingRate.date, FundingRate.value)
                .where(FundingRate.series_id == series_id)
                .order_by(FundingRate.date)
            ).all()
        return _to_series(rows)
    return _loader


def _funding_stress():
    """
    Estrés de financiación = SOFR − EFFR (puntos %). Cuando el repo con colateral
    (SOFR) trepa por encima del interbancario (EFFR), hay escasez de financiación
    /colateral. Disponible desde 2018 (inicio del SOFR). Capta el pico de repo de
    septiembre-2019 y el estrés de marzo-2020.
    """
    sofr = _funding("SOFR")()
    effr = _funding("EFFR")()
    df = pd.concat({"sofr": sofr, "effr": effr}, axis=1).dropna()
    if df.empty:
        return pd.Series(dtype="float64")
    return df["sofr"] - df["effr"]


def _nfci_series(indicator: str):
    def _loader():
        with get_session() as s:
            rows = s.execute(
                select(NFCIReading.date, NFCIReading.value)
                .where(NFCIReading.indicator_name == indicator)
                .order_by(NFCIReading.date)
            ).all()
        return _to_series(rows)
    return _loader


def _to_series(rows) -> pd.Series:
    if not rows:
        return pd.Series(dtype="float64")
    df = pd.DataFrame(rows, columns=["date", "value"])
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")["value"].sort_index()


SERIES: dict[str, dict] = {
    "sp500":       {"loader": _market_close("^GSPC"),   "native": "daily",
                    "direction": 1,  "label": "S&P 500"},
    "btc":         {"loader": _market_close("BTC-USD"), "native": "daily",
                    "direction": 1,  "label": "Bitcoin (USD)"},
    "fed_treast":  {"loader": _fed_series("TREAST"),    "native": "weekly",
                    "direction": 1,  "label": "Fed Treasuries"},
    "fed_feddt":   {"loader": _fed_series("FEDDT"),     "native": "weekly",
                    "direction": 1,  "label": "Fed Agency Debt"},
    "fed_mbs":     {"loader": _fed_series("WSHOMCB"),   "native": "weekly",
                    "direction": 1,  "label": "Fed MBS"},
    "fed_soma":    {"loader": _fed_soma,                "native": "weekly",
                    "direction": 1,  "label": "Fed Securities Held Outright"},
    # NFCI: dirección -1 (más alto = MENOS liquidez). Ver diccionario/metodología.
    "nfci":        {"loader": _nfci_series("NFCI"),        "native": "weekly",
                    "direction": -1, "label": "NFCI (Chicago Fed)"},
    "nfci_credit": {"loader": _nfci_series("NFCICREDIT"),  "native": "weekly",
                    "direction": -1, "label": "NFCI Credit"},
    # Componentes de liquidez neta (millones USD). WALCL inyecta (+); TGA y RRP drenan.
    "walcl":       {"loader": _liquidity_series("WALCL"),     "native": "weekly",
                    "direction": 1,  "label": "Balance total Fed (WALCL)"},
    "tga":         {"loader": _liquidity_series("WTREGEN"),   "native": "weekly",
                    "direction": -1, "label": "Treasury General Account (TGA)"},
    "rrp":         {"loader": _liquidity_series("RRPONTSYD"), "native": "daily",
                    "direction": -1, "label": "Reverse Repo overnight (RRP)"},
    # Serie derivada: WALCL − TGA − RRP, ya alineada a semanal.
    "net_liquidity": {"loader": _net_liquidity,              "native": "weekly",
                    "direction": 1,  "label": "Liquidez neta (WALCL−TGA−RRP)"},
    # Reservas bancarias: liquidez "cantidad" utilizable (mejor proxy que fed_soma).
    "reserves":     {"loader": _liquidity_series("WRESBAL"), "native": "weekly",
                    "direction": 1,  "transform": "diff", "publish_lag_weeks": 0,
                    "label": "Reservas bancarias"},
    # Señales de mercado basadas en PRECIO (no se revisan → sin sesgo look-ahead).
    # Crédito en NIVEL = prima de riesgo (contrarian): spread ancho → retorno futuro +.
    # (En cambios era ruido; el nivel funciona, sobre todo post-2020.)
    "credit":       {"loader": _signal("BAA10Y"),           "native": "daily",
                    "direction": 1,  "transform": "level", "publish_lag_weeks": 0,
                    "label": "Spread crédito Baa−10a"},
    "curve":        {"loader": _signal("T10Y2Y"),           "native": "daily",
                    "direction": 1,  "transform": "level", "publish_lag_weeks": 0,
                    "label": "Curva 10a−2a"},              # signo ambiguo, a estudiar
    "vix":          {"loader": _signal("VIXCLS"),           "native": "daily",
                    "direction": 1,  "transform": "level", "publish_lag_weeks": 0,
                    "label": "VIX"},   # nivel alto → prima de riesgo (retorno futuro +)
    # Liquidez de FINANCIACIÓN (capa 2, foco del usuario). Tipos y estrés repo.
    "sofr":         {"loader": _funding("SOFR"),            "native": "daily",
                    "direction": 0,  "transform": "level", "publish_lag_weeks": 0,
                    "label": "SOFR"},
    "funding_stress": {"loader": _funding_stress,           "native": "daily",
                    "direction": -1, "transform": "level", "publish_lag_weeks": 0,
                    "label": "Estrés financiación (SOFR−EFFR)"},  # ↑ = escasez = risk-off
    # Emisión de letras del Tesoro (hipótesis del usuario: engrasa el repo/liquidez).
    "bill_issuance": {"loader": _bill_issuance,              "native": "weekly",
                    "direction": 1,  "transform": "diff", "publish_lag_weeks": 0,
                    "label": "Emisión T-bills (4s móvil)"},
    # Stock de letras en circulación (nivel). La serie que "se parece" a la bolsa.
    "bills_outstanding": {"loader": _bills_outstanding,     "native": "weekly",
                    "direction": 1,  "transform": "diff", "publish_lag_weeks": 0,
                    "label": "Letras en circulación (stock)"},
    # Actividad y riesgo del repo tri-party (MENSUAL, ~2-3 semanas de retardo).
    "repo_total":   {"loader": _repo_group("Total"),        "native": "monthly",
                    "direction": 1,  "transform": "diff", "publish_lag_weeks": 3,
                    "label": "Volumen repo tri-party (Total)"},
    "repo_risk_share": {"loader": _repo_risk_share,         "native": "monthly",
                    "direction": 1,  "transform": "level", "publish_lag_weeks": 3,
                    "label": "% colateral repo de riesgo"},
    # Haircut del colateral de riesgo: ↑ = menos apalancamiento = risk-off.
    # Señal negativa persistente en BTC (activo más sensible al apalancamiento).
    "repo_haircut": {"loader": _repo_haircut,               "native": "monthly",
                    "direction": -1, "transform": "level", "publish_lag_weeks": 3,
                    "label": "Haircut colateral riesgo (repo)"},
    # Ciclo real / materias primas. WTI es semanal y limpio; COPPER es mensual
    # interpolado (valores planos entre meses). GOLD/SILVER no están en la DB.
    "wti":          {"loader": _commodity("WTI"),           "native": "weekly",
                    "direction": 1,  "transform": "pct_change", "publish_lag_weeks": 0,
                    "label": "Petróleo WTI"},
    "copper":       {"loader": _commodity("COPPER"),        "native": "monthly",
                    "direction": 1,  "transform": "pct_change", "publish_lag_weeks": 0,
                    "label": "Cobre (mensual interp.)"},
}

# Transformación por defecto para el scorecard (si no está en el registro).
DEFAULT_TRANSFORM = {"sp500": "pct_change", "btc": "pct_change"}


def series_meta(key: str, field: str, default=None):
    """Lee un metadato del registro con valor por defecto."""
    return SERIES.get(key, {}).get(field, default)


def transform_for(key: str) -> str:
    """Transformación a aplicar a una serie como predictor (ver methodology.md §2)."""
    t = series_meta(key, "transform")
    if t:
        return t
    return DEFAULT_TRANSFORM.get(key, "diff")


def available() -> list[str]:
    """Claves de series disponibles en el motor."""
    return list(SERIES.keys())


def load_series(key: str) -> pd.Series:
    """Carga una serie por su clave, indexada por fecha (frecuencia nativa)."""
    if key not in SERIES:
        raise KeyError(
            f"Serie '{key}' desconocida. Disponibles: {', '.join(SERIES)}"
        )
    s = SERIES[key]["loader"]()
    s.name = key
    return s


def build_weekly_frame(
    keys: list[str],
    freq: str = WEEKLY_FREQ,
    how: str = "last",
    ffill: bool = True,
    dropna: bool = True,
) -> pd.DataFrame:
    """
    Alinea varias series a una rejilla semanal común.

    Args:
        keys:  claves de SERIES a incluir.
        freq:  rejilla temporal (por defecto 'W-FRI', ver methodology.md).
        how:   agregación intra-semana ('last' por defecto para niveles/precios).
        ffill: propagar hacia delante las series de baja frecuencia hasta el
               siguiente dato real (rellena huecos semanales de series semanales
               publicadas otro día).
        dropna: eliminar filas con algún NaN (recorta al periodo común a todas).

    Returns:
        DataFrame con índice semanal y una columna por clave.
    """
    if not keys:
        raise ValueError("keys no puede estar vacío")

    cols = {}
    for key in keys:
        s = load_series(key)
        if s.empty:
            cols[key] = s
            continue
        resampled = getattr(s.resample(freq), how)()
        if ffill:
            resampled = resampled.ffill()
        cols[key] = resampled

    df = pd.DataFrame(cols)
    if dropna:
        df = df.dropna(how="any")
    return df
