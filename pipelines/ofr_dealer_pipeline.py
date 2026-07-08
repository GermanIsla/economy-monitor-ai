# pipelines/ofr_dealer_pipeline.py
# Pipeline ETL: financiación repo de los primary dealers (FR2004 / dataset NYPD de la OFR).
# Fuente: Office of Financial Research (Short-Term Funding Monitor). API pública, JSON, sin key.
#   Endpoint de serie: https://data.financialresearch.gov/v1/series/timeseries/?mnemonic=<X>
#   Respuesta: array plano [[YYYY-MM-DD, valor], ...]  (SEMANAL, 2015–2021).
#
# RP = REPO (securities out); RRP = REVERSE REPO (securities in). Por colateral y tenor.

from datetime import date, datetime, timedelta
import requests
from sqlalchemy.dialects.sqlite import insert

from pipelines.base import BasePipeline
from db.models.ofr_dealer import OFRDealerFinancing
from db.engine import get_session
from config.settings import SOURCES
from utils.rate_limiter import RateLimiter

FLOW_LABELS = {
    "REPO": "Repo (securities out — el dealer toma efectivo)",
    "REVERSE_REPO": "Reverse repo (securities in — el dealer presta efectivo)",
}
COLLATERAL_LABELS = {
    "TOT":     "Total",
    "T":       "Tesoro (total)",
    "T_eTIPS": "Tesoro (excl. TIPS)",
    "TIPS":    "TIPS",
    "AG":      "Agencia (total)",
    "AG_MBS":  "MBS de agencia",
    "AG_eMBS": "Deuda de agencia (excl. MBS)",
    "CORD":    "Deuda corporativa",
    "EQT":     "Renta variable",
    "ABS":     "ABS (titulizaciones)",
    "OS":      "Otros valores",
}
TENOR_LABELS = {
    "TOT":  "Todos los plazos",
    "OO":   "Overnight & Open",
    "L30":  "≤ 30 días",
    "GE30": "> 30 días",
}

_PREFIX_TO_FLOW = {"RP": "REPO", "RRP": "REVERSE_REPO"}
# Colaterales cuyo total (por tenor TOT) traemos para composición y líneas.
_COLLATERALS = ["T", "T_eTIPS", "TIPS", "AG", "AG_MBS", "AG_eMBS", "CORD", "EQT", "ABS", "OS"]
# Tenores del total agregado (colateral = TOT).
_TENORS = ["OO", "L30", "GE30"]


def _build_series() -> dict:
    """
    {mnemonic: (flow, collateral, tenor)}. Catálogo curado:
      - Total general               → RP_TOT           (TOT, TOT)
      - Total por tenor             → RP_OO/L30/GE30    (TOT, tenor)
      - Total por colateral         → RP_<COL>_TOT      (COL, TOT)
    """
    series = {}
    for prefix, flow in _PREFIX_TO_FLOW.items():
        base = f"NYPD-PD_{prefix}"
        series[f"{base}_TOT-A"] = (flow, "TOT", "TOT")
        for ten in _TENORS:
            series[f"{base}_{ten}-A"] = (flow, "TOT", ten)
        for col in _COLLATERALS:
            series[f"{base}_{col}_TOT-A"] = (flow, col, "TOT")
    return series


SERIES = _build_series()
OBSERVATION_START = "2015-01-01"


class OFRDealerPipeline(BasePipeline):
    """Descarga la financiación repo/reverse-repo de los primary dealers (NYPD, RP/RRP)."""

    min_interval_hours = 100.0  # Datos semanales (además discontinuados en 2021).

    def __init__(self):
        super().__init__()
        config = SOURCES.get("ofr_dealer", {})
        self.base_url = config.get(
            "base_url", "https://data.financialresearch.gov/v1/series/timeseries/"
        )
        self.limiter = RateLimiter(min_interval=config.get("rate_limit", 1.0))

    @property
    def name(self) -> str:
        return "ofr_dealer"

    # ------------------------------------------------------------------
    # EXTRACT
    # ------------------------------------------------------------------
    def extract(self, since_date: date | None = None) -> dict:
        start = OBSERVATION_START
        if since_date:
            start = (since_date - timedelta(days=21)).isoformat()

        all_data = {}
        for mnemonic in SERIES:
            params = {"mnemonic": mnemonic, "start_date": start}
            self.logger.info(f"Descargando {mnemonic} desde OFR (NYPD)...")
            self.limiter.wait()
            try:
                resp = requests.get(self.base_url, params=params, timeout=30)
                resp.raise_for_status()
                pairs = resp.json()
                if isinstance(pairs, list):
                    all_data[mnemonic] = pairs
                    self.logger.info(f"  → {len(pairs)} observaciones")
                else:
                    self.logger.warning(f"  Formato inesperado para {mnemonic}: {type(pairs)}")
            except requests.exceptions.RequestException as e:
                self.logger.error(f"Error descargando {mnemonic}: {e}")

        if not all_data:
            raise ConnectionError("No se pudo descargar ninguna serie NYPD de la OFR")
        return all_data

    # ------------------------------------------------------------------
    # TRANSFORM
    # ------------------------------------------------------------------
    def transform(self, raw_data: dict) -> list[dict]:
        records = []
        for mnemonic, pairs in raw_data.items():
            meta = SERIES.get(mnemonic)
            if not meta:
                continue
            flow, collateral, tenor = meta
            for pair in pairs or []:
                try:
                    d_str, raw_val = pair[0], pair[1]
                    if raw_val is None:          # None = confidencial / sin actividad
                        continue
                    records.append({
                        "date": datetime.strptime(d_str, "%Y-%m-%d").date(),
                        "mnemonic": mnemonic,
                        "flow": flow,
                        "collateral": collateral,
                        "tenor": tenor,
                        "value": float(raw_val) * 1e-6,   # dólares → millones USD
                        "unit": "millions USD",
                    })
                except (ValueError, KeyError, TypeError, IndexError) as e:
                    self.logger.warning(f"Registro inválido en {mnemonic}: {pair} — {e}")

        self.logger.info(f"transform(): {len(records)} registros válidos")
        return records

    # ------------------------------------------------------------------
    # LOAD
    # ------------------------------------------------------------------
    def load(self, records: list[dict]) -> int:
        if not records:
            return 0
        with get_session() as session:
            for row in records:
                stmt = insert(OFRDealerFinancing).values(**row)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["date", "mnemonic"],
                    set_={"value": stmt.excluded.value, "unit": stmt.excluded.unit},
                )
                session.execute(stmt)
            session.commit()
        self.logger.info(f"load(): {len(records)} filas en ofr_dealer_financing")
        return len(records)
