# pipelines/signals_pipeline.py
# Pipeline ETL: indicadores de mercado basados en precio (FRED).
# HY OAS, pendiente de curva, VIX. Sin sesgo de revisión (son precios).

import os
from datetime import date, datetime
import requests
from sqlalchemy.dialects.sqlite import insert

from pipelines.base import BasePipeline
from db.models.signals import MarketSignal
from db.engine import get_session
from config.settings import SOURCES
from utils.rate_limiter import RateLimiter

# series_id FRED → (nombre, unidad)
# Nota: el HY OAS de ICE (BAMLH0A0HYM2) solo tiene histórico desde 2023 en FRED
# (restricción de licencia de ICE). Usamos BAA10Y (spread Baa de Moody's − 10a),
# equivalente conceptual de riesgo de crédito, con histórico desde 1986.
SIGNAL_SERIES = {
    "BAA10Y":  ("Spread de crédito Baa − 10a", "%"),
    "T10Y2Y":  ("Curva de tipos 10a−2a",       "%"),
    "VIXCLS":  ("VIX (volatilidad implícita)", "índice"),
}

OBSERVATION_START = "1990-01-01"


class SignalsPipeline(BasePipeline):
    """Indicadores de mercado basados en precio desde FRED (diarios)."""

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
        return "signals"

    def extract(self, since_date: date | None = None) -> dict:
        if not self.api_key:
            raise ValueError("FRED_API_KEY no configurada")
        all_data = {}
        for series_id in SIGNAL_SERIES:
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
            name, unit = SIGNAL_SERIES.get(series_id, (series_id, ""))
            for o in obs:
                try:
                    records.append({
                        "date": datetime.strptime(o["date"], "%Y-%m-%d").date(),
                        "series_id": series_id, "series_name": name,
                        "value": float(o["value"]), "unit": unit,
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
                stmt = insert(MarketSignal).values(**row)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["date", "series_id"],
                    set_={"value": stmt.excluded.value},
                )
                session.execute(stmt)
            session.commit()
        self.logger.info(f"load(): {len(records)} filas en market_signals")
        return len(records)
