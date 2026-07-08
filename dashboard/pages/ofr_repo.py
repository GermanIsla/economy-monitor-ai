# dashboard/pages/ofr_repo.py
# Página: Repo USA (OFR) — U.S. Repo Markets Data Release del Short-Term Funding Monitor.
# Fuente: Office of Financial Research (pipeline `ofr_repo`). Modelo: OFRRepoSeries.
#
# Muestra los tres venues del repo garantizado de EE. UU. (DVP bilateral compensado,
# GCF y tri-party) por VOLUMEN y TASA — la dimensión que la fuente NY Fed no da.

import dash
from dash import html, dcc, callback, Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd
from sqlalchemy import select
from db.engine import get_session
from db.models.ofr_repo import OFRRepoSeries
from dashboard.components.charts import (
    apply_standard_layout, empty_figure, add_sp500_reference,
)

dash.register_page(
    __name__,
    path="/ofr-repo",
    name="Repo USA (OFR)",
    title="Economy Monitor | Repo USA (OFR)",
)

# Estilo por venue.
VENUES = {
    "DVP": {"nombre": "DVP (bilateral compensado)", "color": "#4c78a8"},
    "GCF": {"nombre": "GCF (interdealer)",          "color": "#54a24b"},
    "TRI": {"nombre": "Tri-party",                  "color": "#e4a23b"},
}

EXPLICACION = """
**¿Qué muestra esta página?**

El **repo garantizado de EE. UU.** visto por la Oficina de Investigación Financiera del
Tesoro (OFR — *Office of Financial Research*), en sus tres canales (*venues*):

- 🔵 **DVP (Delivery-versus-Payment):** repo bilateral **compensado** vía FICC. Aquí el
  prestatario elige el título concreto → es el canal por el que los **hedge funds** montan
  apalancamiento (*basis trade* del Tesoro). El de mayor volumen (~$3 billones/día).
- 🟢 **GCF (General Collateral Finance):** mercado **interdealer** de colateral general.
- 🟠 **Tri-party:** se negocia contra **clases** de colateral (no títulos concretos). Es el
  canal de financiación de los grandes tenedores (fondos monetarios → dealers).

**Métricas:**
- **Volumen negociado (TV):** dólares de repo nuevo iniciado ese día.
- **Volumen vivo (OV):** saldo total pendiente (solo DVP y GCF).
- **Tasa media ponderada (AR):** en %, por tenor (overnight/open, ≤30 días, >30 días).

**¿Por qué importa para el estudio?** El *nivel* y sobre todo los **picos** de la tasa DVP
señalan **escasez de garantía/reservas** (estrés de financiación), y el volumen mide cuánto
apalancamiento está montado en el sistema. Complementa a la página **Repo** (NY Fed), que da
la *composición del colateral* y el *haircut*; aquí tienes *tasa y plazo por venue*.

**Ojo:** son datos **diarios desde 2018**; versión *preliminar* (se revisa con rezago).

💡 En todos los gráficos se superpone el **S&P 500** (línea gris, eje derecho) como
referencia de bolsa. Para **ocultarlo o mostrarlo**, haz clic en *"S&P 500 (dcho.)"* en la
leyenda del gráfico.
"""


# ------------------------------------------------------------------
# Layout
# ------------------------------------------------------------------
layout = dbc.Container([
    html.H2("Repo USA — OFR", className="mb-1"),
    html.P(
        "Mercado de repo garantizado de EE. UU. por venue (DVP, GCF, tri-party): "
        "volumen y tasa. Fuente: Office of Financial Research (Tesoro EE. UU.).",
        className="text-muted mb-4",
    ),
    html.Hr(),

    # --- Filtro de periodo ---
    dbc.Row([
        dbc.Col([
            html.Label("Periodo:", className="fw-bold"),
            dcc.Dropdown(
                id="ofr-periodo-filter",
                options=[
                    {"label": "1 año", "value": 365},
                    {"label": "3 años", "value": 1095},
                    {"label": "5 años", "value": 1825},
                    {"label": "Todo el histórico (2018–)", "value": 0},
                ],
                value=1095,
                clearable=False,
                style={"width": "260px"},
            ),
        ], width="auto"),
    ], className="mb-4"),

    # --- KPI cards (último volumen negociado + tasa por venue) ---
    dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6(VENUES["DVP"]["nombre"], className="text-muted small mb-1"),
            html.H4(id="ofr-kpi-dvp-vol", className="mb-0", style={"color": VENUES["DVP"]["color"]}),
            html.Small(id="ofr-kpi-dvp-rate", className="text-muted"),
        ])), md=4, className="mt-1"),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6(VENUES["GCF"]["nombre"], className="text-muted small mb-1"),
            html.H4(id="ofr-kpi-gcf-vol", className="mb-0", style={"color": VENUES["GCF"]["color"]}),
            html.Small(id="ofr-kpi-gcf-rate", className="text-muted"),
        ])), md=4, className="mt-1"),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6(VENUES["TRI"]["nombre"], className="text-muted small mb-1"),
            html.H4(id="ofr-kpi-tri-vol", className="mb-0", style={"color": VENUES["TRI"]["color"]}),
            html.Small(id="ofr-kpi-tri-rate", className="text-muted"),
        ])), md=4, className="mt-1"),
    ], className="mb-4"),

    # --- Volumen negociado por venue ---
    dbc.Row([dbc.Col([
        html.H4("Volumen negociado por venue", className="mb-2"),
        html.P("Repo nuevo iniciado cada día, en billones de dólares. Mide cuánta "
               "financiación (y apalancamiento) se mueve por cada canal.",
               className="text-muted small mb-3"),
        dbc.Card(dbc.CardBody(dcc.Graph(id="ofr-vol-chart", style={"height": "420px"}))),
    ], width=12)], className="mb-4"),

    # --- Tasa media por venue ---
    dbc.Row([dbc.Col([
        html.H4("Tasa media ponderada por venue", className="mb-2"),
        html.P("Coste del repo overnight/total en %. Sus picos delatan escasez de "
               "garantía o de reservas (estrés de financiación).",
               className="text-muted small mb-3"),
        dbc.Card(dbc.CardBody(dcc.Graph(id="ofr-rate-chart", style={"height": "420px"}))),
    ], width=12)], className="mb-4"),

    # --- DVP en detalle: estructura de tenor de la tasa ---
    dbc.Row([dbc.Col([
        html.H4("DVP — estructura de plazos de la tasa", className="mb-2"),
        html.P("Tasa DVP por vencimiento: total, overnight & open, ≤30 días y >30 días. "
               "Cuando la curva se invierte (corto > largo) suele haber tensión.",
               className="text-muted small mb-3"),
        dbc.Card(dbc.CardBody(dcc.Graph(id="ofr-dvp-tenor-chart", style={"height": "420px"}))),
    ], width=12)], className="mb-4"),

    # --- DVP volumen negociado vs vivo ---
    dbc.Row([dbc.Col([
        html.H4("DVP — volumen negociado vs. saldo vivo", className="mb-2"),
        html.P("Flujo diario (negociado) frente al saldo total pendiente (vivo). El saldo "
               "vivo aproxima el apalancamiento acumulado en el canal bilateral.",
               className="text-muted small mb-3"),
        dbc.Card(dbc.CardBody(dcc.Graph(id="ofr-dvp-flow-chart", style={"height": "420px"}))),
    ], width=12)], className="mb-4"),

    # --- Texto explicativo colapsable ---
    dbc.Row([dbc.Col([
        dbc.Button("📖 ¿Qué significa esta página?", id="ofr-collapse-btn",
                   color="secondary", outline=True, size="sm", className="mb-2"),
        dbc.Collapse(
            dbc.Card(dbc.CardBody(dcc.Markdown(EXPLICACION)), className="mt-1 border-secondary"),
            id="ofr-collapse", is_open=False,
        ),
    ], width=12)], className="mb-5"),

], fluid=True)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _load_df(periodo_dias: int) -> pd.DataFrame:
    """Carga ofr_repo_series a un DataFrame, filtrado por periodo."""
    with get_session() as session:
        stmt = select(OFRRepoSeries).order_by(OFRRepoSeries.date)
        results = session.execute(stmt).scalars().all()

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame([{
        "date": r.date, "venue": r.venue, "metric": r.metric,
        "segment": r.segment, "value": r.value,
    } for r in results])
    df["date"] = pd.to_datetime(df["date"])

    if periodo_dias and periodo_dias > 0:
        limite = pd.Timestamp.now().normalize() - pd.Timedelta(days=periodo_dias)
        df = df[df["date"] >= limite]
    return df


def _series(df, venue, metric, segment):
    """Devuelve el sub-DataFrame (date, value) de una serie concreta, ordenado."""
    sub = df[(df.venue == venue) & (df.metric == metric) & (df.segment == segment)]
    return sub.sort_values("date")


def _fmt_vol(millions: float) -> str:
    """Millones USD → texto en billones (10¹²) o miles de millones (10⁹)."""
    if millions is None or millions != millions:
        return "N/A"
    if abs(millions) >= 1e6:
        return f"${millions / 1e6:,.2f} B"      # billones (trillion)
    return f"${millions / 1e3:,.0f} MM"          # miles de millones (billion)


# ------------------------------------------------------------------
# Callbacks
# ------------------------------------------------------------------
@callback(
    Output("ofr-vol-chart", "figure"),
    Output("ofr-rate-chart", "figure"),
    Output("ofr-dvp-tenor-chart", "figure"),
    Output("ofr-dvp-flow-chart", "figure"),
    Output("ofr-kpi-dvp-vol", "children"),
    Output("ofr-kpi-dvp-rate", "children"),
    Output("ofr-kpi-gcf-vol", "children"),
    Output("ofr-kpi-gcf-rate", "children"),
    Output("ofr-kpi-tri-vol", "children"),
    Output("ofr-kpi-tri-rate", "children"),
    Input("ofr-periodo-filter", "value"),
)
def update_ofr(periodo_dias):
    df = _load_df(periodo_dias)
    if df.empty:
        empty = empty_figure("Sin datos — ejecuta: python run_pipeline.py ofr_repo --full")
        return (empty, empty, empty, empty, "N/A", "", "N/A", "", "N/A", "")


    # --- Volumen negociado por venue (billones USD) ---
    fig_vol = go.Figure()
    for v, cfg in VENUES.items():
        sub = _series(df, v, "TV", "TOT")
        if sub.empty:
            continue
        fig_vol.add_trace(go.Scatter(
            x=sub["date"], y=sub["value"] / 1e6, name=cfg["nombre"], mode="lines",
            line={"color": cfg["color"], "width": 1.6},
            hovertemplate=f"<b>{cfg['nombre']}</b><br>%{{x|%Y-%m-%d}}<br>"
                          f"$%{{y:,.2f}} B<extra></extra>",
        ))
    apply_standard_layout(fig_vol, None)
    fig_vol.update_layout(yaxis_title="Billones USD (10¹²)", xaxis_title="",
                          hovermode="x unified", legend={"orientation": "h", "y": -0.15})

    # --- Tasa media por venue (%) ---
    fig_rate = go.Figure()
    for v, cfg in VENUES.items():
        sub = _series(df, v, "AR", "TOT")
        if sub.empty:
            continue
        fig_rate.add_trace(go.Scatter(
            x=sub["date"], y=sub["value"], name=cfg["nombre"], mode="lines",
            line={"color": cfg["color"], "width": 1.6},
            hovertemplate=f"<b>{cfg['nombre']}</b><br>%{{x|%Y-%m-%d}}<br>"
                          f"%{{y:.2f}}%<extra></extra>",
        ))
    apply_standard_layout(fig_rate, None)
    fig_rate.update_layout(yaxis_title="Tasa media (%)", xaxis_title="",
                           hovermode="x unified", legend={"orientation": "h", "y": -0.15})

    # --- DVP: estructura de tenor de la tasa ---
    tenores = [
        ("TOT",  "Total",            "#4c78a8"),
        ("OO",   "Overnight & Open", "#72b7b2"),
        ("LE30", "≤ 30 días",        "#f2b701"),
        ("G30",  "> 30 días",        "#e45756"),
    ]
    fig_tenor = go.Figure()
    for seg, label, color in tenores:
        sub = _series(df, "DVP", "AR", seg)
        if sub.empty:
            continue
        fig_tenor.add_trace(go.Scatter(
            x=sub["date"], y=sub["value"], name=label, mode="lines",
            line={"color": color, "width": 1.5},
            hovertemplate=f"<b>DVP {label}</b><br>%{{x|%Y-%m-%d}}<br>%{{y:.2f}}%<extra></extra>",
        ))
    apply_standard_layout(fig_tenor, None)
    fig_tenor.update_layout(yaxis_title="Tasa DVP (%)", xaxis_title="",
                            hovermode="x unified", legend={"orientation": "h", "y": -0.15})

    # --- DVP: volumen negociado vs saldo vivo ---
    fig_flow = go.Figure()
    tv = _series(df, "DVP", "TV", "TOT")
    ov = _series(df, "DVP", "OV", "TOT")
    if not tv.empty:
        fig_flow.add_trace(go.Scatter(
            x=tv["date"], y=tv["value"] / 1e6, name="Negociado (flujo diario)", mode="lines",
            line={"color": "#4c78a8", "width": 1.5},
            hovertemplate="<b>Negociado</b><br>%{x|%Y-%m-%d}<br>$%{y:,.2f} B<extra></extra>",
        ))
    if not ov.empty:
        fig_flow.add_trace(go.Scatter(
            x=ov["date"], y=ov["value"] / 1e6, name="Vivo (saldo pendiente)", mode="lines",
            line={"color": "#e45756", "width": 1.5, "dash": "dot"},
            hovertemplate="<b>Vivo</b><br>%{x|%Y-%m-%d}<br>$%{y:,.2f} B<extra></extra>",
        ))
    apply_standard_layout(fig_flow, None)
    fig_flow.update_layout(yaxis_title="Billones USD (10¹²)", xaxis_title="",
                           hovermode="x unified", legend={"orientation": "h", "y": -0.15})

    # --- S&P 500 de referencia en cada gráfico (toggle por leyenda) ---
    for f in (fig_vol, fig_rate, fig_tenor, fig_flow):
        add_sp500_reference(f, periodo_dias)

    # --- KPIs ---
    def kpi(venue):
        vol = _series(df, venue, "TV", "TOT")
        rate = _series(df, venue, "AR", "TOT")
        vol_txt = _fmt_vol(vol["value"].iloc[-1]) if not vol.empty else "N/A"
        if not rate.empty:
            rate_txt = html.Span(f"Tasa media {rate['value'].iloc[-1]:.2f}% · "
                                 f"{rate['date'].iloc[-1]:%d-%m-%Y}")
        else:
            rate_txt = ""
        return vol_txt, rate_txt

    dvp_v, dvp_r = kpi("DVP")
    gcf_v, gcf_r = kpi("GCF")
    tri_v, tri_r = kpi("TRI")

    return (fig_vol, fig_rate, fig_tenor, fig_flow,
            dvp_v, dvp_r, gcf_v, gcf_r, tri_v, tri_r)


@callback(
    Output("ofr-collapse", "is_open"),
    Input("ofr-collapse-btn", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_explicacion(n_clicks):
    return (n_clicks or 0) % 2 == 1
