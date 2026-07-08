# db/models/ofr_dealer.py
# Modelo para la FINANCIACIÓN REPO de los primary dealers de EE. UU.
# Fuente: NY Fed Primary Dealer Statistics (formulario FR2004), dataset NYPD de la OFR.
#
# Es el libro repo real de los dealers y el "repo bilateral" más cercano al NCCBR
# (que no es descargable). Captura la crisis repo de septiembre de 2019 (pico ~$2,6 B).
#
#   RP  → REPO          (securities out: el dealer entrega colateral y toma efectivo).
#   RRP → REVERSE_REPO  (securities in:  el dealer entrega efectivo y recibe colateral).
#
# ⚠️ Serie DISCONTINUADA: la granularidad por colateral/tenor del FR2004 se publica hasta
# ~dic-2021. Tras la revisión de 2022, la financiación repo de dealers pasó al formato por
# venue, que ya recogemos en `ofr_repo_series` (DVP/GCF/tri-party). Se conserva por su
# valor histórico (2015–2021), sobre todo el episodio de estrés de 2019.

from sqlalchemy import String, Float, Date, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base, TimestampMixin


class OFRDealerFinancing(Base, TimestampMixin):
    """
    Financiación repo semanal de los primary dealers (FR2004 / dataset NYPD), formato largo.

    Descomposición del mnemónico:
      - `flow`       : REPO (RP) o REVERSE_REPO (RRP).
      - `collateral` : TOT, T, T_eTIPS, TIPS, AG, AG_MBS, AG_eMBS, CORD, EQT, ABS, OS.
      - `tenor`      : TOT (todos), OO (overnight&open), L30 (≤30 días), GE30 (>30 días).

    Unidad: **millones USD** (la API los da en dólares brutos → ÷1e6). Volúmenes brutos,
    semanales. Los None de la fuente (edición por confidencialidad o sin actividad) se
    descartan en el pipeline.
    """
    __tablename__ = "ofr_dealer_financing"
    __table_args__ = (
        UniqueConstraint('date', 'mnemonic', name='uq_ofr_dealer_financing'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[Date] = mapped_column(Date, nullable=False, index=True)
    mnemonic: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    flow: Mapped[str] = mapped_column(String(14), nullable=False, index=True)   # REPO / REVERSE_REPO
    collateral: Mapped[str] = mapped_column(String(10), nullable=False)         # TOT / T / AG / ...
    tenor: Mapped[str] = mapped_column(String(6), nullable=False)               # TOT / OO / L30 / GE30
    value: Mapped[float] = mapped_column(Float, nullable=False)                 # millones USD
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="millions USD")
