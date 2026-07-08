# pipelines/ofr_sponsored_pipeline.py
# Pipeline ETL: repo patrocinado (FICC Sponsored Service).
# Fuente: OFR Hedge Fund Monitor, API pública JSON sin key.
#   Endpoint: https://data.financialresearch.gov/hf/v1/series/timeseries/?mnemonic=<X>
#   Respuesta: array plano [[YYYY-MM-DD, valor], ...]  (~diario, 2020–2025).
#
# OJO: API distinta del Short-Term Funding Monitor (base .../hf/ en vez de .../v1/).

from datetime import date, datetime, timedelta
import requests
from sqlalchemy.dialects.sqlite import insert

from pipelines.base import BasePipeline
from db.models.ofr_sponsored import OFRSponsoredRepo
from db.engine import get_session
from config.settings import SOURCES
from utils.rate_limiter import RateLimiter

# mnemónico → flujo
SERIES = {
    "FICC-SPONSORED_REPO_VOL":    "REPO",
    "FICC-SPONSORED_REVREPO_VOL": "REVERSE_REPO",
}
FLOW_LABELS = {
    "REPO": "Repo patrocinado (hedge fund toma efectivo)",
    "REVERSE_REPO": "Reverse repo patrocinado (fondo monetario presta efectivo)",
}
OBSERVATION_START = "2020-01-01"


class OFRSponsoredPipeline(BasePipeline):
    """Descarga el volumen de repo/reverse-repo del FICC Sponsored Service (OFR HFM)."""

    min_interval_hours = 100.0  # Publicación con rezago; refresco semanal holgado.

    def __init__(self):
        super().__init__()
        config = SOURCES.get("ofr_sponsored", {})
        self.base_url = config.get(
            "base_url", "https://data.financialresearch.gov/hf/v1/series/timeseries/"
        )
        self.limiter = RateLimiter(min_interval=config.get("rate_limit", 1.0))

    @property
    def name(self) -> str:
        return "ofr_sponsored"

    def extract(self, since_date: date | None = None) -> dict:
        start = OBSERVATION_START
        if since_date:
            start = (since_date - timedelta(days=14)).isoformat()

        all_data = {}
        for mnemonic in SERIES:
            params = {"mnemonic": mnemonic, "start_date": start}
            self.logger.info(f"Descargando {mnemonic} desde OFR (Hedge Fund Monitor)...")
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
            raise ConnectionError("No se pudo descargar el sponsored repo de la OFR")
        return all_data

    def transform(self, raw_data: dict) -> list[dict]:
        records = []
        for mnemonic, pairs in raw_data.items():
            flow = SERIES.get(mnemonic)
            if not flow:
                continue
            for pair in pairs or []:
                try:
                    d_str, raw_val = pair[0], pair[1]
                    if raw_val is None:
                        continue
                    records.append({
                        "date": datetime.strptime(d_str, "%Y-%m-%d").date(),
                        "flow": flow,
                        "value": float(raw_val) * 1e-6,   # dólares → millones USD
                        "unit": "millions USD",
                    })
                except (ValueError, KeyError, TypeError, IndexError) as e:
                    self.logger.warning(f"Registro inválido en {mnemonic}: {pair} — {e}")

        self.logger.info(f"transform(): {len(records)} registros válidos")
        return records

    def load(self, records: list[dict]) -> int:
        if not records:
            return 0
        with get_session() as session:
            for row in records:
                stmt = insert(OFRSponsoredRepo).values(**row)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["date", "flow"],
                    set_={"value": stmt.excluded.value, "unit": stmt.excluded.unit},
                )
                session.execute(stmt)
            session.commit()
        self.logger.info(f"load(): {len(records)} filas en ofr_sponsored_repo")
        return len(records)
