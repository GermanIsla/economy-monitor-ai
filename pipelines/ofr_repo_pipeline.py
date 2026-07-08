# pipelines/ofr_repo_pipeline.py
# Pipeline ETL: U.S. Repo Markets Data Release de la OFR (Short-Term Funding Monitor).
# Fuente: Office of Financial Research (Tesoro de EE. UU.).
#   API REST pública, JSON, sin API key.
#   Endpoint de serie: https://data.financialresearch.gov/v1/series/timeseries/?mnemonic=<X>
#   Respuesta: array plano [[YYYY-MM-DD, valor], ...]  (diario).
#
# Cubre los tres venues del repo garantizado USA: DVP (bilateral compensado),
# GCF y tri-party (TRI), con tasa media (AR), volumen negociado (TV) y volumen vivo (OV).

from datetime import date, datetime
import requests
from sqlalchemy.dialects.sqlite import insert

from pipelines.base import BasePipeline
from db.models.ofr_repo import OFRRepoSeries
from db.engine import get_session
from config.settings import SOURCES
from utils.rate_limiter import RateLimiter

# Etiquetas legibles para descomponer el mnemónico OFR.
VENUE_LABELS = {
    "DVP": "DVP (bilateral compensado, FICC)",
    "GCF": "GCF (General Collateral Finance)",
    "TRI": "Tri-party",
}
METRIC_LABELS = {
    "AR": "Tasa media ponderada",
    "TV": "Volumen negociado",
    "OV": "Volumen vivo",
}
SEGMENT_LABELS = {
    "TOT":  "Total",
    "OO":   "Overnight & Open",
    "T":    "A plazo (term)",
    "G30":  "Vencimiento > 30 días",
    "LE30": "Vencimiento ≤ 30 días",
}

# Catálogo curado de series a descargar (vintage PRELIMINAR '-P', llega hasta ayer).
# Cada entrada: mnemónico → (venue, metric, segment). El resto se deriva.
#
# Priorizamos el headline de cada venue (total, overnight, estructura de tenor) para
# tener una foto completa sin traer los ~160 mnemónicos. Ampliable en el futuro.
SERIES = {
    # --- DVP: bilateral compensado (el canal de apalancamiento hedge funds) ---
    "REPO-DVP_AR_TOT-P":  ("DVP", "AR", "TOT"),
    "REPO-DVP_TV_TOT-P":  ("DVP", "TV", "TOT"),
    "REPO-DVP_OV_TOT-P":  ("DVP", "OV", "TOT"),
    "REPO-DVP_AR_OO-P":   ("DVP", "AR", "OO"),
    "REPO-DVP_TV_OO-P":   ("DVP", "TV", "OO"),
    "REPO-DVP_AR_LE30-P": ("DVP", "AR", "LE30"),
    "REPO-DVP_AR_G30-P":  ("DVP", "AR", "G30"),
    # --- GCF: interdealer, general collateral ---
    "REPO-GCF_AR_TOT-P":  ("GCF", "AR", "TOT"),
    "REPO-GCF_TV_TOT-P":  ("GCF", "TV", "TOT"),
    "REPO-GCF_OV_TOT-P":  ("GCF", "OV", "TOT"),
    "REPO-GCF_AR_OO-P":   ("GCF", "AR", "OO"),
    "REPO-GCF_TV_OO-P":   ("GCF", "TV", "OO"),
    # --- TRI: tri-party (no publica volumen vivo OV) ---
    "REPO-TRI_AR_TOT-P":  ("TRI", "AR", "TOT"),
    "REPO-TRI_TV_TOT-P":  ("TRI", "TV", "TOT"),
    "REPO-TRI_AR_OO-P":   ("TRI", "AR", "OO"),
    "REPO-TRI_TV_OO-P":   ("TRI", "TV", "OO"),
}

# Unidad/normalización por métrica.
#   AR: porcentaje, tal cual.
#   TV/OV: la API los da en dólares en bruto → ÷1e6 para pasar a millones USD.
METRIC_UNIT = {
    "AR": ("percent", 1.0),
    "TV": ("millions USD", 1e-6),
    "OV": ("millions USD", 1e-6),
}

# La OFR arranca este release en 2018-05.
OBSERVATION_START = "2018-01-01"


class OFRRepoPipeline(BasePipeline):
    """
    Descarga las series curadas del U.S. Repo Markets Data Release (OFR) y las
    almacena en formato largo, normalizando volúmenes a millones USD.
    """

    min_interval_hours = 20.0  # Release preliminar diario (15:00 ET). Refresco diario.

    def __init__(self):
        super().__init__()
        config = SOURCES.get("ofr_repo", {})
        self.base_url = config.get(
            "base_url", "https://data.financialresearch.gov/v1/series/timeseries/"
        )
        self.limiter = RateLimiter(min_interval=config.get("rate_limit", 1.0))

    @property
    def name(self) -> str:
        return "ofr_repo"

    # ------------------------------------------------------------------
    # EXTRACT
    # ------------------------------------------------------------------
    def extract(self, since_date: date | None = None) -> dict:
        """
        Descarga cada serie del catálogo. Devuelve {mnemonic: [[fecha, valor], ...]}.

        Modo incremental: pide desde `since_date` con solape de unos días para
        recapturar la revisión preliminar→final. El dataset es pequeño, así que el
        coste de traer todo el histórico también es bajo.
        """
        start = OBSERVATION_START
        if since_date:
            # Solape defensivo de 10 días para recoger revisiones del preliminar.
            from datetime import timedelta
            start = (since_date - timedelta(days=10)).isoformat()

        all_data = {}
        for mnemonic in SERIES:
            params = {"mnemonic": mnemonic, "start_date": start}
            self.logger.info(f"Descargando {mnemonic} desde OFR...")
            self.limiter.wait()
            try:
                resp = requests.get(self.base_url, params=params, timeout=30)
                resp.raise_for_status()
                pairs = resp.json()
                # La respuesta es un array plano [[fecha, valor], ...].
                if isinstance(pairs, list):
                    all_data[mnemonic] = pairs
                    self.logger.info(f"  → {len(pairs)} observaciones")
                else:
                    self.logger.warning(f"  Formato inesperado para {mnemonic}: {type(pairs)}")
            except requests.exceptions.RequestException as e:
                self.logger.error(f"Error descargando {mnemonic}: {e}")

        if not all_data:
            raise ConnectionError("No se pudo descargar ninguna serie de la OFR")
        return all_data

    # ------------------------------------------------------------------
    # TRANSFORM
    # ------------------------------------------------------------------
    def transform(self, raw_data: dict) -> list[dict]:
        """Aplana a filas y normaliza (volúmenes → millones USD, tasas → %)."""
        records = []
        for mnemonic, pairs in raw_data.items():
            meta = SERIES.get(mnemonic)
            if not meta:
                continue
            venue, metric, segment = meta
            unit, factor = METRIC_UNIT[metric]

            for pair in pairs or []:
                try:
                    d_str, raw_val = pair[0], pair[1]
                    if raw_val is None:
                        continue
                    records.append({
                        "date": datetime.strptime(d_str, "%Y-%m-%d").date(),
                        "mnemonic": mnemonic,
                        "venue": venue,
                        "metric": metric,
                        "segment": segment,
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
        """UPSERT por (date, mnemonic): reescribe el valor (revisión preliminar→final)."""
        if not records:
            return 0

        with get_session() as session:
            for row in records:
                stmt = insert(OFRRepoSeries).values(**row)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["date", "mnemonic"],
                    set_={"value": stmt.excluded.value, "unit": stmt.excluded.unit},
                )
                session.execute(stmt)
            session.commit()

        self.logger.info(f"load(): {len(records)} filas en ofr_repo_series")
        return len(records)
