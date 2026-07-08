# pipelines/ofr_rates_pipeline.py
# Pipeline ETL: tasas de referencia NY Fed con percentiles y volumen (dataset FNYR de la OFR).
# Fuente: Office of Financial Research (Short-Term Funding Monitor). API pública, JSON, sin key.
#   Endpoint de serie: https://data.financialresearch.gov/v1/series/timeseries/?mnemonic=<X>
#   Respuesta: array plano [[YYYY-MM-DD, valor], ...]  (diario, 2018-04–hoy).
#
# Aporta los PICOS de estrés que el nivel medio esconde: percentiles 1/25/75/99 y volumen
# de SOFR, BGCR y TGCR (repo garantizado), más EFFR/OBFR (no garantizado) para spreads.

from datetime import date, datetime, timedelta
import requests
from sqlalchemy.dialects.sqlite import insert

from pipelines.base import BasePipeline
from db.models.ofr_rates import OFRReferenceRate
from db.engine import get_session
from config.settings import SOURCES
from utils.rate_limiter import RateLimiter

RATE_LABELS = {
    "SOFR": "SOFR (repo garantizado amplio)",
    "BGCR": "Broad General Collateral Rate (repo)",
    "TGCR": "Tri-party General Collateral Rate (repo)",
    "EFFR": "Effective Fed Funds Rate (no garantizado)",
    "OBFR": "Overnight Bank Funding Rate (no garantizado)",
}
STAT_LABELS = {
    "LEVEL":  "Tasa publicada",
    "P1":     "Percentil 1",
    "P25":    "Percentil 25",
    "P75":    "Percentil 75",
    "P99":    "Percentil 99",
    "VOLUME": "Volumen negociado",
}

# Sufijos del mnemónico FNYR → estadístico.
_SUFFIX_TO_STAT = {
    "":       "LEVEL",
    "_1Pctl":  "P1",
    "_25Pctl": "P25",
    "_75Pctl": "P75",
    "_99Pctl": "P99",
    "_UV":     "VOLUME",
}

# Catálogo curado. Para los tipos repo (SOFR/BGCR/TGCR) traemos TODO (nivel, 4 percentiles,
# volumen). Para los no garantizados (EFFR/OBFR) solo el nivel, como referencia de spread.
_FULL_STATS = ["", "_1Pctl", "_25Pctl", "_75Pctl", "_99Pctl", "_UV"]


def _build_series() -> dict:
    """Construye {mnemonic: (rate, stat)} a partir del catálogo."""
    series = {}
    for rate in ["SOFR", "BGCR", "TGCR"]:
        for suf in _FULL_STATS:
            series[f"FNYR-{rate}{suf}-A"] = (rate, _SUFFIX_TO_STAT[suf])
    for rate in ["EFFR", "OBFR"]:
        series[f"FNYR-{rate}-A"] = (rate, "LEVEL")
    return series


SERIES = _build_series()

# Normalización por estadístico: percentiles/nivel en %, volumen (UV) a millones USD.
def _unit_factor(stat: str):
    if stat == "VOLUME":
        return "millions USD", 1e-6
    return "percent", 1.0


OBSERVATION_START = "2018-01-01"


class OFRRatesPipeline(BasePipeline):
    """Descarga las tasas de referencia NY Fed (FNYR) con percentiles y volumen."""

    min_interval_hours = 20.0  # Publicación diaria (~08:00 ET). Refresco diario.

    def __init__(self):
        super().__init__()
        config = SOURCES.get("ofr_rates", {})
        self.base_url = config.get(
            "base_url", "https://data.financialresearch.gov/v1/series/timeseries/"
        )
        self.limiter = RateLimiter(min_interval=config.get("rate_limit", 1.0))

    @property
    def name(self) -> str:
        return "ofr_rates"

    # ------------------------------------------------------------------
    # EXTRACT
    # ------------------------------------------------------------------
    def extract(self, since_date: date | None = None) -> dict:
        """Descarga cada serie del catálogo. Devuelve {mnemonic: [[fecha, valor], ...]}."""
        start = OBSERVATION_START
        if since_date:
            start = (since_date - timedelta(days=10)).isoformat()

        all_data = {}
        for mnemonic in SERIES:
            params = {"mnemonic": mnemonic, "start_date": start}
            self.logger.info(f"Descargando {mnemonic} desde OFR (FNYR)...")
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
            raise ConnectionError("No se pudo descargar ninguna serie FNYR de la OFR")
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
            rate, stat = meta
            unit, factor = _unit_factor(stat)
            for pair in pairs or []:
                try:
                    d_str, raw_val = pair[0], pair[1]
                    if raw_val is None:
                        continue
                    records.append({
                        "date": datetime.strptime(d_str, "%Y-%m-%d").date(),
                        "mnemonic": mnemonic,
                        "rate": rate,
                        "stat": stat,
                        "value": float(raw_val) * factor,
                        "unit": unit,
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
                stmt = insert(OFRReferenceRate).values(**row)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["date", "mnemonic"],
                    set_={"value": stmt.excluded.value, "unit": stmt.excluded.unit},
                )
                session.execute(stmt)
            session.commit()
        self.logger.info(f"load(): {len(records)} filas en ofr_reference_rates")
        return len(records)
