# db/models/liquidity.py
# Modelo para las series de LIQUIDEZ NETA del sistema financiero USA.
# Fuente: FRED. Componentes de la ecuación: Liquidez neta ≈ WALCL − TGA − RRP.

from sqlalchemy import String, Float, Date, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base, TimestampMixin


class LiquiditySeries(Base, TimestampMixin):
    """
    Series de liquidez del sistema (FRED), normalizadas a la MISMA unidad.

    Componentes de la liquidez neta:
      - WALCL     → Balance total de la Fed (inyecta liquidez)
      - WTREGEN   → Treasury General Account / TGA (drena)
      - RRPONTSYD → Reverse Repo overnight / RRP (drena)

    IMPORTANTE — unidad: **todos los valores se almacenan en MILLONES USD (10⁶)**.
    FRED entrega WALCL y WTREGEN en millones, pero RRPONTSYD en miles de millones;
    el pipeline convierte el RRP (×1000) al cargar para que las tres sean restables
    directamente. La columna `unit` deja constancia ("millions USD").
    """
    __tablename__ = "liquidity_series"
    __table_args__ = (
        UniqueConstraint('date', 'series_id', name='uq_liquidity_series'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    series_id: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    series_name: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)   # millones USD (normalizado)
    unit: Mapped[str] = mapped_column(String(30), nullable=False, default="millions USD")
