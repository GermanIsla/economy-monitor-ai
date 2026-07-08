# db/models/ofr_rates.py
# Modelo para las TASAS DE REFERENCIA de la Reserva Federal de Nueva York
# publicadas por la OFR (dataset FNYR del Short-Term Funding Monitor).
#
# Incluye lo que faltaba del backlog: los **percentiles** (1/25/75/99) y el
# **volumen** de cada tasa — es decir, los PICOS de estrés que el nivel medio esconde.
#
# Tasas cubiertas (foco en repo garantizado):
#   - SOFR : Secured Overnight Financing Rate (repo garantizado amplio, benchmark).
#   - BGCR : Broad General Collateral Rate (repo GC amplio).
#   - TGCR : Tri-Party General Collateral Rate (repo GC tri-party).
#   - EFFR/OBFR: tipos NO garantizados, como referencia para spreads (SOFR−EFFR).

from sqlalchemy import String, Float, Date, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base, TimestampMixin


class OFRReferenceRate(Base, TimestampMixin):
    """
    Serie diaria de tasa de referencia NY Fed (dataset FNYR de la OFR), formato largo.

    Columnas de descomposición del mnemónico:
      - `rate` : familia de tasa (SOFR / BGCR / TGCR / EFFR / OBFR).
      - `stat` : estadístico → LEVEL (tasa publicada), P1/P25/P75/P99 (percentiles de la
                 distribución intradía de operaciones), VOLUME (volumen negociado).

    Unidades (normalizadas por el pipeline):
      - stat en {LEVEL, P1, P25, P75, P99} → **porcentaje** (`unit='percent'`).
      - stat = 'VOLUME'                    → **millones USD** (`unit='millions USD'`;
                                              la API lo da en dólares brutos → ÷1e6).

    La distancia P99−LEVEL (o P99−P1) mide la **cola de la distribución**: cuando se
    dispara, hay operaciones puntuales muy por encima → escasez de garantía / estrés
    de financiación (p. ej. el pico repo de septiembre de 2019).
    """
    __tablename__ = "ofr_reference_rates"
    __table_args__ = (
        UniqueConstraint('date', 'mnemonic', name='uq_ofr_reference_rates'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    mnemonic: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    rate: Mapped[str] = mapped_column(String(10), nullable=False, index=True)   # SOFR/BGCR/...
    stat: Mapped[str] = mapped_column(String(8), nullable=False)                # LEVEL/P99/VOLUME
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
