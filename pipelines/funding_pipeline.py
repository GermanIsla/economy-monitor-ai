# pipelines/funding_pipeline.py
# Pipeline ETL: tipos de financiación a corto (repo/interbancario) desde FRED.
# SOFR, EFFR, IORB → base para los spreads de estrés de financiación.

import os
from datetime import date, datetime
import requests
from sqlalchemy.dialects.sqlite import insert

from pipelines.base import BasePipeline
from db.models.funding import FundingRate
from db.engine import get_session
from config.settings import SOURCES
from utils.rate_limiter import RateLimiter

FUNDING_SERIES = {
    "SOFR": "Secured Overnight Financing Rate",
    "EFFR": "Effective Federal Funds Rate",
    "IORB": "Interest on Reserve Balances",
}

OBSERVATION_START = "2014-01-01"


class FundingPipeline(BasePipeline):
    """Tipos de financiación a corto desde FRED (diarios)."""

    min_interval_hours = 20.0

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
        return "funding"

    def extract(self, since_date: date | None = None) -> dict:
        if not self.api_key:
            raise ValueError("FRED_API_KEY no configurada")
        all_data = {}
        for series_id in FUNDING_SERIES:
            params = {
                "series_id": series_id, "api_key": self.api_key,
                "file_type": "json", "sort_order": "asc",
                "observation_start": since_date.isoformat() if since_date else OBSERVATION_START,
            }
            self.logger.info(f"Descargando serie {series_id} desde FRED...")
            self.limiter.wait()
            resp = requests.get(self.base_url, params=params, timeout=30)
            resp.raise_for_status()
            obs = resp.json().get("observations", [])
            valid = [{"date": o["date"], "value": o["value"]}
                     for o in obs if o.get("value", ".") != "."]
            all_data[series_id] = valid
            self.logger.info(f"  → {len(valid)} observaciones para {series_id}")
        return all_data

    def transform(self, raw_data: dict) -> list[dict]:
        records = []
        for series_id, obs in raw_data.items():
            name = FUNDING_SERIES.get(series_id, series_id)
            for o in obs:
                try:
                    records.append({
                        "date": datetime.strptime(o["date"], "%Y-%m-%d").date(),
                        "series_id": series_id, "series_name": name,
                        "value": float(o["value"]),
                    })
                except (ValueError, KeyError, TypeError) as e:
                    self.logger.warning(f"Registro inválido en {series_id}: {o} — {e}")
        self.logger.info(f"transform(): {len(records)} registros válidos")
        return records

    def load(self, records: list[dict]) -> int:
        if not records:
            return 0
        with get_session() as session:
            for row in records:
                stmt = insert(FundingRate).values(**row)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["date", "series_id"],
                    set_={"value": stmt.excluded.value},
                )
                session.execute(stmt)
            session.commit()
        self.logger.info(f"load(): {len(records)} filas en funding_rates")
        return len(records)
