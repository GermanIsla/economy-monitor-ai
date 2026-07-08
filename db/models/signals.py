# db/models/signals.py
# Indicadores de mercado BASADOS EN PRECIO (no se revisan, disponibles en tiempo real).
# Fuente: FRED. Alternativa "honesta" a índices re-estimados como el NFCI.

from sqlalchemy import String, Float, Date, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base, TimestampMixin


class MarketSignal(Base, TimestampMixin):
    """
    Series de riesgo/condiciones basadas en precio de mercado:
      - BAMLH0A0HYM2 → Spread High Yield (OAS), en %
      - T10Y2Y       → Pendiente de la curva 10a−2a, en %
      - VIXCLS       → VIX (volatilidad implícita), índice

    Ventaja frente a índices como el NFCI: son precios, **no se revisan** a posteriori,
    así que no sufren sesgo de anticipación (look-ahead) en el backtest.
    """
    __tablename__ = "market_signals"
    __table_args__ = (
        UniqueConstraint('date', 'series_id', name='uq_market_signal'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    series_id: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    series_name: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False, default="")
