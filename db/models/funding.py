# db/models/funding.py
# Liquidez de FINANCIACIÓN (capa 2 del marco): tipos del mercado monetario/repo.
# Fuente: FRED. El foco principal del usuario ("la sangre de las venas financieras").

from sqlalchemy import String, Float, Date, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base, TimestampMixin


class FundingRate(Base, TimestampMixin):
    """
    Tipos del mercado de financiación a corto (repo/interbancario), en %:
      - SOFR → Secured Overnight Financing Rate (repo con colateral de Tesoro)
      - EFFR → Effective Federal Funds Rate (interbancario sin colateral)
      - IORB → Interest on Reserve Balances (suelo que paga la Fed)

    El ESTRÉS de financiación se mide con spreads (derivados en el motor):
      SOFR − EFFR y SOFR − IORB. Cuando el repo con colateral (SOFR) sube por
      encima del interbancario/suelo, hay escasez de financiación/colateral.
    """
    __tablename__ = "funding_rates"
    __table_args__ = (
        UniqueConstraint('date', 'series_id', name='uq_funding_rate'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    series_id: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    series_name: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)  # %
