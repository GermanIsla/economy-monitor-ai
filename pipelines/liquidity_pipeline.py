# pipelines/liquidity_pipeline.py
# Pipeline ETL: componentes de la LIQUIDEZ NETA del sistema financiero USA (FRED).
# Series: WALCL (balance Fed), WTREGEN (TGA), RRPONTSYD (Reverse Repo).
#
# Liquidez neta ≈ WALCL − WTREGEN − RRPONTSYD  (todo en millones USD tras normalizar).

import os
import json
import requests
from datetime import date, datetime
from sqlalchemy.dialects.sqlite import insert

from pipelines.base import BasePipeline
from db.models.liquidity import LiquiditySeries
from db.engine import get_session
from config.settings import SOURCES
from utils.rate_limiter import RateLimiter

# series_id FRED → (nombre descriptivo, factor a millones USD)
#   WALCL, WTREGEN vienen en millones → factor 1.
#   RRPONTSYD viene en miles de millones (billions) → ×1000 para pasar a millones.
LIQUIDITY_SERIES = {
    "WALCL":     ("Balance total de la Fed (activos)", 1.0),
    "WTREGEN":   ("Treasury General Account (TGA)",    1.0),
    "RRPONTSYD": ("Reverse Repo overnight (RRP)",      1000.0),
    # Reservas bancarias: la liquidez "cantidad" utilizable. FRED WRESBAL ya
    # viene en millones USD → factor 1.0 (verificado: ult ≈ 2,97 millones de M = $2,97B).
    "WRESBAL":   ("Reservas bancarias en la Fed",      1.0),
}

# FRED tiene histórico largo; empezamos en 2002 como el resto del proyecto.
OBSERVATION_START = "2002-01-01"


class LiquidityPipeline(BasePipeline):
    """
    Descarga los tres componentes de la liquidez neta desde FRED y los normaliza
    todos a millones USD, de modo que WALCL − TGA − RRP sea una resta directa.
    """

    min_interval_hours = 20.0  # RRP es diaria; WALCL/TGA semanales. Refresco diario.

    def __init__(self):
        super().__init__()
        config = SOURCES.get("fred", {})
        self.limiter = RateLimiter(min_interval=config.get("rate_limit", 0.5))

        from dotenv import load_dotenv
        load_dotenv()
        self.api_key = os.getenv("FRED_API_KEY")
        if not self.api_key:
            self.logger.error("FRED_API_KEY no encontrada en .env")
        self.base_url = "https://api.stlouisfed.org/fred/series/observations"

    @property
    def name(self) -> str:
        return "liquidity"

    # ------------------------------------------------------------------
    # EXTRACT
    # ------------------------------------------------------------------
    def extract(self, since_date: date | None = None) -> dict:
        """Descarga observaciones de cada serie. {series_id: [{date, value}, ...]}."""
        if not self.api_key:
            raise ValueError("FRED_API_KEY no configurada")

        all_data = {}
        for series_id in LIQUIDITY_SERIES:
            params = {
                "series_id": series_id,
                "api_key": self.api_key,
                "file_type": "json",
                "sort_order": "asc",
                "observation_start": OBSERVATION_START,
            }
            # Modo incremental: solape de unos días para recapturar revisiones.
            if since_date:
                params["observation_start"] = since_date.isoformat()

            self.logger.info(f"Descargando serie {series_id} desde FRED...")
            self.limiter.wait()

            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            observations = response.json().get("observations", [])

            valid = [
                {"date": obs["date"], "value": obs["value"]}
                for obs in observations
                if obs.get("value", ".") != "."
            ]
            all_data[series_id] = valid
            self.logger.info(f"  → {len(valid)} observaciones para {series_id}")

        return all_data

    # ------------------------------------------------------------------
    # TRANSFORM
    # ------------------------------------------------------------------
    def transform(self, raw_data: dict) -> list[dict]:
        """Normaliza a millones USD (aplica el factor por serie) y aplana."""
        records = []
        for series_id, observations in raw_data.items():
            series_name, factor = LIQUIDITY_SERIES.get(series_id, (series_id, 1.0))
            for obs in observations:
                try:
                    records.append({
                        "date": datetime.strptime(obs["date"], "%Y-%m-%d").date(),
                        "series_id": series_id,
                        "series_name": series_name,
                        "value": float(obs["value"]) * factor,  # → millones USD
                        "unit": "millions USD",
                    })
                except (ValueError, KeyError, TypeError) as e:
                    self.logger.warning(f"Registro inválido en {series_id}: {obs} — {e}")

        self.logger.info(f"transform(): {len(records)} registros válidos")
        return records

    # ------------------------------------------------------------------
    # LOAD
    # ------------------------------------------------------------------
    def load(self, records: list[dict]) -> int:
        """UPSERT por (date, series_id): actualiza el valor si ya existe."""
        if not records:
            return 0

        with get_session() as session:
            for row in records:
                stmt = insert(LiquiditySeries).values(**row)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["date", "series_id"],
                    set_={"value": stmt.excluded.value, "unit": stmt.excluded.unit},
                )
                session.execute(stmt)
            session.commit()

        self.logger.info(f"load(): {len(records)} filas en liquidity_series")
        return len(records)
