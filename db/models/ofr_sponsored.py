# db/models/ofr_sponsored.py
# Modelo para el REPO PATROCINADO (FICC Sponsored Service).
# Fuente: OFR Hedge Fund Monitor (API `/hf/`), dataset `ficc`.
#
# El sponsored repo es el canal por el que un dealer miembro de FICC "patrocina" a una
# contraparte no-dealer (típicamente un HEDGE FUND o un FONDO MONETARIO) para que acceda
# a la compensación central: el fondo monetario presta efectivo y el hedge fund lo toma,
# con FICC de contraparte. Es una de las vías de apalancamiento más vigiladas.

from sqlalchemy import String, Float, Date, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base, TimestampMixin


class OFRSponsoredRepo(Base, TimestampMixin):
    """
    Volumen del FICC Sponsored Service, visto desde el sponsored member.

      - flow = REPO         → volumen de repo patrocinado.
      - flow = REVERSE_REPO → volumen de reverse repo patrocinado.

    Unidad: **millones USD** (la API los da en dólares brutos → ÷1e6). Frecuencia ~diaria,
    2020–2025 (con rezago de publicación). Ojo: se solapa parcialmente con el venue DVP de
    `ofr_repo_series` (el sponsored es una parte del repo bilateral compensado); no sumar sin más.
    """
    __tablename__ = "ofr_sponsored_repo"
    __table_args__ = (
        UniqueConstraint('date', 'flow', name='uq_ofr_sponsored_repo'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    flow: Mapped[str] = mapped_column(String(14), nullable=False, index=True)   # REPO / REVERSE_REPO
    value: Mapped[float] = mapped_column(Float, nullable=False)                 # millones USD
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="millions USD")
