# pipelines/indices_pipeline.py
# Descarga precios diarios de índices/activos globales desde Yahoo Finance.
# Primer alcance: S&P 500 (^GSPC) y Bitcoin (BTC-USD).

from datetime import date, datetime, timedelta

import yfinance as yf
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert

from config.settings import SOURCES
from db.engine import get_session
from db.models.indices import MarketIndex
from pipelines.base import BasePipeline
from utils.rate_limiter import RateLimiter

# ---------------------------------------------------------------------------
# Símbolos a descargar → nombre legible
#
#   ^GSPC   → índice S&P 500 (nivel del índice, sin dividendos)
#   BTC-USD → precio spot de Bitcoin en dólares (cotiza 24/7)
#
# Ambos encajan en el modelo MarketIndex (OHLCV diario). Añadir más símbolos
# aquí siguiendo el mismo patrón (NASDAQ ^IXIC, DAX ^GDAXI, oro GC=F, etc.).
# ---------------------------------------------------------------------------
INDICES = {
    '^GSPC':   'S&P 500',
    'BTC-USD': 'Bitcoin (USD)',
}


def _to_float(val) -> float | None:
    """Convierte a float nativo; NaN/None → None."""
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    # NaN no es igual a sí mismo
    return f if f == f else None


class IndicesPipeline(BasePipeline):
    """
    Pipeline de índices globales desde Yahoo Finance (yfinance).

    Yahoo no exige API key. En modo incremental descarga solo desde la última
    ejecución exitosa (con un pequeño solape para capturar revisiones del cierre
    del día); en modo --full descarga todo el histórico disponible.
    """

    # Datos diarios. El cierre del S&P se consolida al final de la sesión de NY;
    # BTC cotiza 24/7. Con ~20h evitamos re-descargas redundantes intradía.
    min_interval_hours = 20.0

    def __init__(self):
        super().__init__()
        config = SOURCES.get('indices', {})
        self.limiter = RateLimiter(min_interval=config.get('rate_limit', 2.0))

    @property
    def name(self) -> str:
        return "indices"

    # ------------------------------------------------------------------
    # EXTRACT — una descarga por símbolo
    # ------------------------------------------------------------------
    def extract(self, since_date: date = None) -> dict:
        """
        Descarga el histórico OHLCV de cada símbolo.

        Retorna {symbol: [{date, open, high, low, close, volume}, ...]} con
        tipos JSON-serializables para poder guardarlo en staging.
        """
        # Solape de unos días para recapturar el cierre revisado del último día.
        start = None
        if since_date:
            start = (since_date - timedelta(days=5)).isoformat()

        results = {}
        for symbol in INDICES:
            self.logger.info(
                f"Descargando {symbol} "
                f"({'desde ' + start if start else 'histórico completo'})..."
            )
            self.limiter.wait()

            ticker = yf.Ticker(symbol)
            if start:
                hist = ticker.history(start=start, auto_adjust=False)
            else:
                hist = ticker.history(period='max', auto_adjust=False)

            if hist is None or hist.empty:
                self.logger.warning(f"  → {symbol}: sin datos devueltos")
                results[symbol] = []
                continue

            rows = []
            for idx, row in hist.iterrows():
                rows.append({
                    'date':   idx.date().isoformat(),
                    'open':   _to_float(row.get('Open')),
                    'high':   _to_float(row.get('High')),
                    'low':    _to_float(row.get('Low')),
                    'close':  _to_float(row.get('Close')),
                    'volume': _to_float(row.get('Volume')),
                })
            results[symbol] = rows
            self.logger.info(f"  → {symbol}: {len(rows)} sesiones")

        return results

    # ------------------------------------------------------------------
    # TRANSFORM
    # ------------------------------------------------------------------
    def transform(self, raw_data: dict) -> list[dict]:
        """Aplana el dict de símbolos a filas del modelo MarketIndex."""
        all_records = []

        for symbol, rows in raw_data.items():
            index_name = INDICES.get(symbol, symbol)
            count = 0
            for r in rows:
                close = _to_float(r.get('close'))
                if close is None:
                    continue  # close es obligatorio; sin él la fila no sirve
                d = r.get('date')
                if isinstance(d, str):
                    d = datetime.strptime(d[:10], '%Y-%m-%d').date()

                all_records.append({
                    'date':         d,
                    'index_symbol': symbol,
                    'index_name':   index_name,
                    'close_price':  close,
                    'open_price':   _to_float(r.get('open')),
                    'high_price':   _to_float(r.get('high')),
                    'low_price':    _to_float(r.get('low')),
                    'volume':       _to_float(r.get('volume')),
                })
                count += 1
            self.logger.info(f"  {symbol}: {count} filas válidas")

        self.logger.info(
            f"Total transformados: {len(all_records)} registros en "
            f"{len(raw_data)} símbolos"
        )
        return all_records

    # ------------------------------------------------------------------
    # LOAD
    # ------------------------------------------------------------------
    def load(self, clean_data: list[dict]) -> int:
        """UPSERT sobre (date, index_symbol): actualiza precios y volumen."""
        if not clean_data:
            return 0

        with get_session() as session:
            for row in clean_data:
                stmt = sqlite_upsert(MarketIndex).values(**row)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['date', 'index_symbol'],
                    set_={
                        'close_price': stmt.excluded.close_price,
                        'open_price':  stmt.excluded.open_price,
                        'high_price':  stmt.excluded.high_price,
                        'low_price':   stmt.excluded.low_price,
                        'volume':      stmt.excluded.volume,
                    },
                )
                session.execute(stmt)
            session.commit()

        self.logger.info(f"Cargados {len(clean_data)} registros en market_indices.")
        return len(clean_data)
