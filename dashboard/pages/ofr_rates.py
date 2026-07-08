# dashboard/pages/ofr_rates.py
# Página: Tasas repo y estrés (OFR) — dataset FNYR del Short-Term Funding Monitor.
# Fuente: Office of Financial Research (pipeline `ofr_rates`). Modelo: OFRReferenceRate.
#
# Muestra las tasas de repo garantizado (SOFR/BGCR/TGCR) y, sobre todo, sus PERCENTILES
# y VOLUMEN: la cola P99 delata los picos de escasez de garantía (estrés de financiación).

import dash
from dash import html, dcc, callback, Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd
from sqlalchemy import select
from db.engine import get_session
from db.models.ofr_rates import OFRReferenceRate
from dashboard.components.charts import (
    apply_standard_layout, empty_figure, add_sp500_reference,
)

dash.register_page(
    __name__,
    path="/ofr-rates",
    name="Tasas repo y estrés (OFR)",
    title="Economy Monitor | Tasas repo (OFR)",
)

# Tasas repo garantizadas y su color.
REPO_RATES = {
    "SOFR": {"nombre": "SOFR (repo amplio)",   "color": "#4c78a8"},
    "BGCR": {"nombre": "BGCR (GC amplio)",      "color": "#54a24b"},
    "TGCR": {"nombre": "TGCR (GC tri-party)",   "color": "#e4a23b"},
}

EXPLICACION = """
**¿Qué muestra esta página?**

Las **tasas de repo garantizado de EE. UU.** publicadas por la Reserva Federal de Nueva York
(vía OFR), con lo que de verdad importa para detectar tensión: sus **percentiles** y su
**volumen**.

- **SOFR** (*Secured Overnight Financing Rate*): el tipo repo de referencia, sobre >$3 billones
  diarios. **BGCR** y **TGCR** son variantes de colateral general (amplio y tri-party).
- **Percentiles (P1–P99):** la tasa publicada es una mediana; el **percentil 99** recoge las
  operaciones más caras del día. Cuando P99 se dispara por encima del nivel, hay **escasez de
  garantía/efectivo** en algún rincón del mercado → **estrés de financiación**.
- **Estrés (P99 − nivel):** el gráfico dedicado aísla esa cola. Su mayor pico histórico es el
  **17-sep-2019 (SOFR P99 = 9,00%)**, la crisis repo que forzó a la Fed a reintervenir.
- **Volumen:** cuánto efectivo se mueve; cae en momentos de estrés (el mercado se congela).

**Para el estudio:** es una señal **episódica/umbral**, no lineal — la información está en los
**picos**, no en el nivel medio. Complementa a la página **Repo USA (OFR)** (volúmenes por
venue) y a **Financiación** (SOFR−EFFR).

💡 En cada gráfico se superpone el **S&P 500** (línea gris, eje derecho) como referencia de
bolsa. Se muestra/oculta con clic en *"S&P 500 (dcho.)"* en la leyenda.
"""


# ------------------------------------------------------------------
# Layout
# ------------------------------------------------------------------
layout = dbc.Container([
    html.H2("Tasas repo y estrés — OFR", className="mb-1"),
    html.P(
        "Tasas de repo garantizado (SOFR, BGCR, TGCR) con percentiles y volumen. "
        "Fuente: Office of Financial Research / NY Fed.",
        className="text-muted mb-4",
    ),
    html.Hr(),

    dbc.Row([
        dbc.Col([
            html.Label("Periodo:", className="fw-bold"),
            dcc.Dropdown(
                id="ofrr-periodo-filter",
                options=[
                    {"label": "1 año", "value": 365},
                    {"label": "3 años", "value": 1095},
                    {"label": "5 años", "value": 1825},
                    {"label": "Todo el histórico (2018–)", "value": 0},
                ],
                value=1095, clearable=False, style={"width": "260px"},
            ),
        ], width="auto"),
    ], className="mb-4"),

    # --- KPIs ---
    dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("SOFR (nivel)", className="text-muted small mb-1"),
            html.H4(id="ofrr-kpi-sofr", className="mb-0", style={"color": "#4c78a8"}),
            html.Small(id="ofrr-kpi-sofr-date", className="text-muted"),
        ])), md=3, className="mt-1"),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("SOFR percentil 99", className="text-muted small mb-1"),
            html.H4(id="ofrr-kpi-p99", className="mb-0", style={"color": "#e45756"}),
            html.Small("cola alta del día", className="text-muted"),
        ])), md=3, className="mt-1"),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("Estrés (P99 − nivel)", className="text-muted small mb-1"),
            html.H4(id="ofrr-kpi-stress", className="mb-0"),
            html.Small("puntos básicos", className="text-muted"),
        ])), md=3, className="mt-1"),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("Volumen SOFR", className="text-muted small mb-1"),
            html.H4(id="ofrr-kpi-vol", className="mb-0", style={"color": "#72b7b2"}),
            html.Small("negociado diario", className="text-muted"),
        ])), md=3, className="mt-1"),
    ], className="mb-4"),

    # --- Tasas repo ---
    dbc.Row([dbc.Col([
        html.H4("Tasas de repo garantizado", className="mb-2"),
        html.P("SOFR, BGCR y TGCR (nivel publicado, %). Se mueven con la política de la Fed; "
               "las divergencias entre ellas señalan fricciones de colateral.",
               className="text-muted small mb-3"),
        dbc.Card(dbc.CardBody(dcc.Graph(id="ofrr-rates-chart", style={"height": "420px"}))),
    ], width=12)], className="mb-4"),

    # --- Banda de percentiles SOFR ---
    dbc.Row([dbc.Col([
        html.H4("SOFR — banda de percentiles (P1–P99)", className="mb-2"),
        html.P("Nivel de SOFR con la banda entre percentil 1 y 99. Cuando la banda se abre "
               "hacia arriba, hay operaciones muy por encima → tensión de garantía.",
               className="text-muted small mb-3"),
        dbc.Card(dbc.CardBody(dcc.Graph(id="ofrr-band-chart", style={"height": "420px"}))),
    ], width=12)], className="mb-4"),

    # --- Estrés (P99 - nivel) ---
    dbc.Row([dbc.Col([
        html.H4("Estrés de financiación (P99 − nivel)", className="mb-2"),
        html.P("La cola alta aislada, en puntos básicos, para SOFR y TGCR. Los picos marcan "
               "episodios de escasez (sep-2019, cierres de trimestre, COVID-marzo 2020).",
               className="text-muted small mb-3"),
        dbc.Card(dbc.CardBody(dcc.Graph(id="ofrr-stress-chart", style={"height": "420px"}))),
    ], width=12)], className="mb-4"),

    # --- Volumen SOFR ---
    dbc.Row([dbc.Col([
        html.H4("Volumen de SOFR", className="mb-2"),
        html.P("Efectivo negociado diario en billones de dólares. Tiende a caer en los "
               "episodios de estrés (el mercado se retrae).",
               className="text-muted small mb-3"),
        dbc.Card(dbc.CardBody(dcc.Graph(id="ofrr-vol-chart", style={"height": "420px"}))),
    ], width=12)], className="mb-4"),

    dbc.Row([dbc.Col([
        dbc.Button("📖 ¿Qué significa esta página?", id="ofrr-collapse-btn",
                   color="secondary", outline=True, size="sm", className="mb-2"),
        dbc.Collapse(
            dbc.Card(dbc.CardBody(dcc.Markdown(EXPLICACION)), className="mt-1 border-secondary"),
            id="ofrr-collapse", is_open=False,
        ),
    ], width=12)], className="mb-5"),

], fluid=True)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _load_df(periodo_dias: int) -> pd.DataFrame:
    with get_session() as session:
        stmt = select(OFRReferenceRate).order_by(OFRReferenceRate.date)
        results = session.execute(stmt).scalars().all()
    if not results:
        return pd.DataFrame()
    df = pd.DataFrame([{
        "date": r.date, "rate": r.rate, "stat": r.stat, "value": r.value,
    } for r in results])
    df["date"] = pd.to_datetime(df["date"])
    if periodo_dias and periodo_dias > 0:
        limite = pd.Timestamp.now().normalize() - pd.Timedelta(days=periodo_dias)
        df = df[df["date"] >= limite]
    return df


def _series(df, rate, stat):
    sub = df[(df.rate == rate) & (df.stat == stat)]
    return sub.sort_values("date")


# ------------------------------------------------------------------
# Callbacks
# ------------------------------------------------------------------
@callback(
    Output("ofrr-rates-chart", "figure"),
    Output("ofrr-band-chart", "figure"),
    Output("ofrr-stress-chart", "figure"),
    Output("ofrr-vol-chart", "figure"),
    Output("ofrr-kpi-sofr", "children"),
    Output("ofrr-kpi-sofr-date", "children"),
    Output("ofrr-kpi-p99", "children"),
    Output("ofrr-kpi-stress", "children"),
    Output("ofrr-kpi-vol", "children"),
    Input("ofrr-periodo-filter", "value"),
)
def update_rates(periodo_dias):
    df = _load_df(periodo_dias)
    if df.empty:
        empty = empty_figure("Sin datos — ejecuta: python run_pipeline.py ofr_rates --full")
        return (empty, empty, empty, empty, "N/A", "", "N/A", "N/A", "N/A")

    # --- Tasas repo (niveles) ---
    fig_rates = go.Figure()
    for rate, cfg in REPO_RATES.items():
        sub = _series(df, rate, "LEVEL")
        if sub.empty:
            continue
        fig_rates.add_trace(go.Scatter(
            x=sub["date"], y=sub["value"], name=cfg["nombre"], mode="lines",
            line={"color": cfg["color"], "width": 1.5},
            hovertemplate=f"<b>{cfg['nombre']}</b><br>%{{x|%Y-%m-%d}}<br>%{{y:.2f}}%<extra></extra>",
        ))
    apply_standard_layout(fig_rates, None)
    fig_rates.update_layout(yaxis_title="Tasa (%)", xaxis_title="",
                            hovermode="x unified", legend={"orientation": "h", "y": -0.15})

    # --- Banda de percentiles SOFR (P1–P99) ---
    fig_band = go.Figure()
    p99 = _series(df, "SOFR", "P99")
    p1 = _series(df, "SOFR", "P1")
    lvl = _series(df, "SOFR", "LEVEL")
    if not p99.empty and not p1.empty:
        fig_band.add_trace(go.Scatter(
            x=p99["date"], y=p99["value"], name="P99", mode="lines",
            line={"color": "rgba(228,87,86,0.0)", "width": 0}, showlegend=True,
            hovertemplate="P99: %{y:.2f}%<extra></extra>",
        ))
        fig_band.add_trace(go.Scatter(
            x=p1["date"], y=p1["value"], name="Banda P1–P99", mode="lines",
            line={"color": "rgba(228,87,86,0.0)", "width": 0},
            fill="tonexty", fillcolor="rgba(228,87,86,0.20)",
            hovertemplate="P1: %{y:.2f}%<extra></extra>",
        ))
    if not lvl.empty:
        fig_band.add_trace(go.Scatter(
            x=lvl["date"], y=lvl["value"], name="SOFR (nivel)", mode="lines",
            line={"color": "#4c78a8", "width": 1.6},
            hovertemplate="SOFR: %{y:.2f}%<extra></extra>",
        ))
    apply_standard_layout(fig_band, None)
    fig_band.update_layout(yaxis_title="Tasa (%)", xaxis_title="",
                           hovermode="x unified", legend={"orientation": "h", "y": -0.15})

    # --- Estrés (P99 − nivel) en puntos básicos, SOFR y TGCR ---
    fig_stress = go.Figure()
    for rate, color in [("SOFR", "#4c78a8"), ("TGCR", "#e4a23b")]:
        lv = _series(df, rate, "LEVEL").set_index("date")["value"]
        p = _series(df, rate, "P99").set_index("date")["value"]
        if lv.empty or p.empty:
            continue
        spread = ((p - lv) * 100).dropna()  # % → puntos básicos
        fig_stress.add_trace(go.Scatter(
            x=spread.index, y=spread.values, name=f"{rate} (P99−nivel)", mode="lines",
            line={"color": color, "width": 1.3},
            hovertemplate=f"<b>{rate}</b><br>%{{x|%Y-%m-%d}}<br>%{{y:.0f}} pb<extra></extra>",
        ))
    apply_standard_layout(fig_stress, None)
    fig_stress.update_layout(yaxis_title="P99 − nivel (puntos básicos)", xaxis_title="",
                             hovermode="x unified", legend={"orientation": "h", "y": -0.15})

    # --- Volumen SOFR ---
    fig_vol = go.Figure()
    vol = _series(df, "SOFR", "VOLUME")
    if not vol.empty:
        fig_vol.add_trace(go.Scatter(
            x=vol["date"], y=vol["value"] / 1e6, name="Volumen SOFR", mode="lines",
            line={"color": "#72b7b2", "width": 1.4}, fill="tozeroy",
            fillcolor="rgba(114,183,178,0.15)",
            hovertemplate="%{x|%Y-%m-%d}<br>$%{y:,.2f} B<extra></extra>",
        ))
    apply_standard_layout(fig_vol, None)
    fig_vol.update_layout(yaxis_title="Billones USD (10¹²)", xaxis_title="",
                          hovermode="x unified", showlegend=False)

    # --- S&P 500 de referencia (toggle por leyenda) ---
    for f in (fig_rates, fig_band, fig_stress, fig_vol):
        add_sp500_reference(f, periodo_dias)

    # --- KPIs ---
    def last(rate, stat):
        s = _series(df, rate, stat)
        return (s["value"].iloc[-1], s["date"].iloc[-1]) if not s.empty else (None, None)

    sofr, sofr_d = last("SOFR", "LEVEL")
    p99v, _ = last("SOFR", "P99")
    volv, _ = last("SOFR", "VOLUME")

    sofr_txt = f"{sofr:.2f}%" if sofr is not None else "N/A"
    sofr_date = f"{sofr_d:%d-%m-%Y}" if sofr_d is not None else ""
    p99_txt = f"{p99v:.2f}%" if p99v is not None else "N/A"
    if sofr is not None and p99v is not None:
        pb = (p99v - sofr) * 100
        color = "text-danger" if pb >= 20 else ("text-warning" if pb >= 8 else "text-success")
        stress_txt = html.Span(f"{pb:+.0f} pb", className=color)
    else:
        stress_txt = "N/A"
    vol_txt = f"${volv / 1e6:,.2f} B" if volv is not None else "N/A"

    return (fig_rates, fig_band, fig_stress, fig_vol,
            sofr_txt, sofr_date, p99_txt, stress_txt, vol_txt)


@callback(
    Output("ofrr-collapse", "is_open"),
    Input("ofrr-collapse-btn", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_explicacion(n_clicks):
    return (n_clicks or 0) % 2 == 1
