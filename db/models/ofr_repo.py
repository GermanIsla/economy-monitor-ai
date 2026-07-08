# db/models/ofr_repo.py
# Modelo para el U.S. Repo Markets Data Release de la OFR
# (Office of Financial Research, Tesoro de EE. UU.) — Short-Term Funding Monitor.
#
# Cubre los tres venues del repo garantizado de EE. UU.:
#   - DVP : Delivery-versus-Payment, bilateral COMPENSADO vía FICC.
#           Es el canal de apalancamiento de los hedge funds (repo especial/GC).
#   - GCF : General Collateral Finance (FICC). Interdealer, puro general collateral.
#   - TRI : tri-party. Se negocia contra CLASES de colateral, no títulos concretos.
#
# Complementa (no sustituye) al repo tri-party de la NY Fed que ya tenemos: aquélla
# da la COMPOSICIÓN de colateral y el haircut; ésta da TASA y TENOR por venue, más el
# venue DVP entero, que faltaba.
#
# Formato LARGO: una fila por (fecha, mnemónico). El mnemónico OFR se descompone en
# venue / metric / segment para poder filtrar cómodamente en el dashboard.

from sqlalchemy import String, Float, Date, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base, TimestampMixin


class OFRRepoSeries(Base, TimestampMixin):
    """
    Serie diaria del U.S. Repo Markets Data Release (OFR).

    Unidades (normalizadas por el pipeline para homogeneizar con el resto del proyecto):
      - metric = 'AR' (Average Rate)        → value en PORCENTAJE      (unit = 'percent')
      - metric = 'TV' (Transaction Volume)  → value en MILLONES USD    (unit = 'millions USD')
      - metric = 'OV' (Outstanding Volume)  → value en MILLONES USD    (unit = 'millions USD')

    La API entrega los volúmenes en dólares en bruto; el pipeline los pasa a millones
    (÷1e6) para que sean comparables con `liquidity_series`, `fed_balance_assets`, etc.

    Vintage: se almacena la serie PRELIMINAR ('-P'), que llega hasta el día anterior.
    La OFR la revisa a versión final con rezago; el UPSERT reescribe el valor si cambia.
    """
    __tablename__ = "ofr_repo_series"
    __table_args__ = (
        UniqueConstraint('date', 'mnemonic', name='uq_ofr_repo_series'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    mnemonic: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    venue: Mapped[str] = mapped_column(String(10), nullable=False, index=True)   # DVP / GCF / TRI
    metric: Mapped[str] = mapped_column(String(4), nullable=False)               # AR / TV / OV
    segment: Mapped[str] = mapped_column(String(12), nullable=False)             # TOT / OO / T / G30 / LE30
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
