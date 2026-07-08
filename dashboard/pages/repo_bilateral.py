# dashboard/pages/repo_bilateral.py
# Página consolidada: REPO BILATERAL (OFR) con apartados en pestañas.
#   1. Venues        → volúmenes y tasas por venue (DVP/GCF/tri-party)   [ofr_repo_series]
#   2. Tasas y estrés→ SOFR/BGCR/TGCR + percentiles + volumen            [ofr_reference_rates]
#   3. Primary dealers→ libro repo/reverse-repo de dealers 2015–2021     [ofr_dealer_financing]
#
# El repo tri-party de la NY Fed (composición de colateral y haircut) vive aparte en /repo.
# Fuente de todo lo de aquí: Office of Financial Research (Short-Term Funding Monitor).

import dash
from dash import html, dcc, callback, Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd
from sqlalchemy import select
from db.engine import get_session
from db.models.ofr_repo import OFRRepoSeries
from db.models.ofr_rates import OFRReferenceRate
from db.models.ofr_dealer import OFRDealerFinancing
from dashboard.components.charts import (
    apply_standard_layout, empty_figure, add_sp500_reference,
)

dash.register_page(
    __name__,
    path="/repo-bilateral",
    name="Repo bilateral",
    title="Economy Monitor | Repo bilateral",
)

VENUES = {
    "DVP": {"nombre": "DVP (bilateral compensado)", "color": "#4c78a8"},
    "GCF": {"nombre": "GCF (interdealer)",          "color": "#54a24b"},
    "TRI": {"nombre": "Tri-party",                  "color": "#e4a23b"},
}
REPO_RATES = {
    "SOFR": {"nombre": "SOFR (repo amplio)", "color": "#4c78a8"},
    "BGCR": {"nombre": "BGCR (GC amplio)",   "color": "#54a24b"},
    "TGCR": {"nombre": "TGCR (GC tri-party)","color": "#e4a23b"},
}
# Colaterales hoja (no solapados) para composición del libro de dealers.
DEALER_COLLAT = [
    ("T_eTIPS", "Tesoro (excl. TIPS)", "#4c78a8"),
    ("TIPS",    "TIPS",                "#72b7b2"),
    ("AG_MBS",  "MBS de agencia",      "#54a24b"),
    ("AG_eMBS", "Deuda de agencia",    "#b2df8a"),
    ("CORD",    "Deuda corporativa",   "#e4a23b"),
    ("EQT",     "Renta variable",      "#e45756"),
    ("ABS",     "ABS",                 "#b07aa1"),
    ("OS",      "Otros valores",       "#9c755f"),
]

EXPLICACION_VENUES = """
**¿Qué es cada cosa en esta pestaña?**

**Venues (canales por los que se hace el repo garantizado de EE. UU.):**
- 🔵 **DVP** *(Delivery-versus-Payment)*: repo **bilateral compensado** vía FICC. El
  prestatario elige el título concreto que da en garantía → es el canal por el que los
  **hedge funds** montan apalancamiento (el *basis trade* del Tesoro). Es el de mayor volumen.
- 🟢 **GCF** *(General Collateral Finance)*: mercado **interdealer** (dealer con dealer) de
  colateral general; no se conoce ni la contraparte ni el título concreto.
- 🟠 **Tri-party**: se negocia contra **clases** de colateral (no títulos concretos), con un
  custodio (BNY) en medio. Es el canal por el que los fondos monetarios prestan efectivo a los dealers.
- 🟣 **Total**: la suma de los tres → el tamaño del mercado de repo garantizado.

**Métricas:**
- **Volumen negociado** (*transaction volume*): dólares de repo **nuevo** iniciado ese día
  (flujo). Mide cuánta financiación se mueve.
- **Tasa media ponderada** (*average rate*, %): el coste medio del repo ese día.
- **Saldo vivo** (*outstanding volume*): el importe total **pendiente** en cada momento (stock),
  no solo lo nuevo del día. Aproxima el apalancamiento acumulado. (Solo DVP y GCF lo publican.)

**Plazos (tenor)** — en el detalle de DVP:
- **Overnight & Open**: a un día o sin vencimiento fijo (renovable a diario). El grueso del repo.
- **≤ 30 días** y **> 30 días**: repo a plazo (*term*). Más plazo = financiación más estable.

**La línea gris (S&P 500, eje derecho)** es solo una referencia de bolsa para comparar; se
oculta/muestra con clic en la leyenda. Todos los importes están en **billones** (10¹²) de dólares.
"""

_PERIODO_OPTS = [
    {"label": "1 año", "value": 365},
    {"label": "3 años", "value": 1095},
    {"label": "5 años", "value": 1825},
    {"label": "Todo el histórico", "value": 0},
]


# ------------------------------------------------------------------
# Layout
# ------------------------------------------------------------------
def _graph(id_):
    return dbc.Card(dbc.CardBody(dcc.Graph(id=id_, style={"height": "400px"})), className="mb-4")


layout = dbc.Container([
    html.H2("Repo bilateral — OFR", className="mb-1"),
    html.P(
        "Mercado de repo garantizado de EE. UU. (Office of Financial Research): venues, "
        "tasas/estrés y el libro de los primary dealers. El tri-party de la NY Fed "
        "(colateral y haircut) está en la página «Repo (NY Fed)».",
        className="text-muted mb-3",
    ),
    dbc.Row([dbc.Col([
        html.Label("Periodo:", className="fw-bold me-2"),
        dcc.Dropdown(id="rb-periodo", options=_PERIODO_OPTS, value=1095,
                     clearable=False, style={"width": "260px"}),
    ], width="auto")], className="mb-3"),
    html.Hr(),

    dbc.Tabs([
        # ---------- TAB 1: Venues ----------
        dbc.Tab(label="Volúmenes por venue", tab_id="tab-venues", children=[
            html.P("Repo por canal: DVP (bilateral compensado, el de los hedge funds), GCF "
                   "(interdealer) y tri-party. Volumen negociado y tasa por venue; detalle "
                   "de DVP por plazo.", className="text-muted small my-3"),
            html.H5("Volumen negociado por venue (billones USD)", className="mb-2"),
            _graph("rb-vol"),
            html.H5("Tasa media por venue (%)", className="mb-2"),
            _graph("rb-rate"),
            html.H5("DVP — estructura de plazos de la tasa", className="mb-2"),
            _graph("rb-dvp-tenor"),
            html.H5("DVP — volumen negociado vs. saldo vivo", className="mb-2"),
            _graph("rb-dvp-flow"),
            dbc.Button("📖 ¿Qué significa cada término?", id="rb-venues-help-btn",
                       color="secondary", outline=True, size="sm", className="my-2"),
            dbc.Collapse(
                dbc.Card(dbc.CardBody(dcc.Markdown(EXPLICACION_VENUES)),
                         className="border-secondary"),
                id="rb-venues-help", is_open=False,
            ),
        ]),

        # ---------- TAB 2: Tasas y estrés ----------
        dbc.Tab(label="Tasas y estrés", tab_id="tab-rates", children=[
            html.P("Tasas de repo garantizado (SOFR/BGCR/TGCR) con percentiles y volumen. "
                   "La cola P99 delata los picos de escasez de garantía (sep-2019).",
                   className="text-muted small my-3"),
            dbc.Row([
                dbc.Col(dbc.Card(dbc.CardBody([
                    html.H6("SOFR (nivel)", className="text-muted small mb-1"),
                    html.H4(id="rb-kpi-sofr", className="mb-0", style={"color": "#4c78a8"}),
                ])), md=3),
                dbc.Col(dbc.Card(dbc.CardBody([
                    html.H6("SOFR P99", className="text-muted small mb-1"),
                    html.H4(id="rb-kpi-p99", className="mb-0", style={"color": "#e45756"}),
                ])), md=3),
                dbc.Col(dbc.Card(dbc.CardBody([
                    html.H6("Estrés (P99−nivel)", className="text-muted small mb-1"),
                    html.H4(id="rb-kpi-stress", className="mb-0"),
                ])), md=3),
                dbc.Col(dbc.Card(dbc.CardBody([
                    html.H6("Volumen SOFR", className="text-muted small mb-1"),
                    html.H4(id="rb-kpi-vol", className="mb-0", style={"color": "#72b7b2"}),
                ])), md=3),
            ], className="my-3"),
            html.H5("Tasas de repo garantizado", className="mb-2"),
            _graph("rb-rates"),
            html.H5("SOFR — banda de percentiles (P1–P99)", className="mb-2"),
            _graph("rb-band"),
            html.H5("Estrés de financiación (P99 − nivel, puntos básicos)", className="mb-2"),
            _graph("rb-stress"),
            html.H5("Volumen de SOFR", className="mb-2"),
            _graph("rb-vol-sofr"),
        ]),

        # ---------- TAB 3: Primary dealers ----------
        dbc.Tab(label="Primary dealers", tab_id="tab-dealers", children=[
            dbc.Alert([
                html.B("Serie histórica (2015–2021). "),
                "El libro repo de los primary dealers (formulario FR2004) es el «repo "
                "bilateral» más cercano al NCCBR (no descargable): ~60% de su reverse repo "
                "es bilateral sin compensar. Tras la revisión de 2022 pasó al formato por "
                "venue → ver la pestaña «Volúmenes por venue» para el dato actual.",
            ], color="secondary", className="my-3 small"),
            dbc.Row([
                dbc.Col(dbc.Card(dbc.CardBody([
                    html.H6("Repo (dealers toman efectivo)", className="text-muted small mb-1"),
                    html.H4(id="rb-kpi-repo", className="mb-0", style={"color": "#4c78a8"}),
                    html.Small(id="rb-kpi-repo-d", className="text-muted"),
                ])), md=4),
                dbc.Col(dbc.Card(dbc.CardBody([
                    html.H6("Reverse repo (dealers prestan)", className="text-muted small mb-1"),
                    html.H4(id="rb-kpi-rrepo", className="mb-0", style={"color": "#e4a23b"}),
                    html.Small(id="rb-kpi-rrepo-d", className="text-muted"),
                ])), md=4),
                dbc.Col(dbc.Card(dbc.CardBody([
                    html.H6("Pico repo histórico", className="text-muted small mb-1"),
                    html.H4(id="rb-kpi-peak", className="mb-0", style={"color": "#e45756"}),
                    html.Small("máx. 2015–2021 (COVID, mar-2020)", className="text-muted"),
                ])), md=4),
            ], className="my-3"),
            html.H5("Repo vs. reverse repo (total, billones USD)", className="mb-2"),
            _graph("rb-dealer-tot"),
            html.H5("Composición del repo por colateral", className="mb-2"),
            _graph("rb-dealer-collat"),
            html.H5("Repo por plazo (overnight vs. term)", className="mb-2"),
            _graph("rb-dealer-tenor"),
        ]),
    ], id="rb-tabs", active_tab="tab-venues"),

    html.Div(className="mb-5"),
], fluid=True)


# ------------------------------------------------------------------
# Loaders
# ------------------------------------------------------------------
def _filter_periodo(df, periodo_dias):
    if periodo_dias and periodo_dias > 0 and not df.empty:
        limite = pd.Timestamp.now().normalize() - pd.Timedelta(days=periodo_dias)
        return df[df["date"] >= limite]
    return df


def _load(model, cols, periodo_dias):
    with get_session() as session:
        results = session.execute(select(model).order_by(model.date)).scalars().all()
    if not results:
        return pd.DataFrame()
    df = pd.DataFrame([{c: getattr(r, c) for c in cols} for r in results])
    df["date"] = pd.to_datetime(df["date"])
    return _filter_periodo(df, periodo_dias)


# ==================================================================
# TAB 1 — Venues
# ==================================================================
@callback(
    Output("rb-venues-help", "is_open"),
    Input("rb-venues-help-btn", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_venues_help(n):
    return (n or 0) % 2 == 1


@callback(
    Output("rb-vol", "figure"), Output("rb-rate", "figure"),
    Output("rb-dvp-tenor", "figure"), Output("rb-dvp-flow", "figure"),
    Input("rb-periodo", "value"),
)
def update_venues(periodo):
    df = _load(OFRRepoSeries, ["date", "venue", "metric", "segment", "value"], periodo)
    if df.empty:
        e = empty_figure("Sin datos — ejecuta: python run_pipeline.py ofr_repo --full")
        return e, e, e, e

    def ser(venue, metric, segment):
        s = df[(df.venue == venue) & (df.metric == metric) & (df.segment == segment)]
        return s.sort_values("date")

    fig_vol = go.Figure()
    for v, cfg in VENUES.items():
        s = ser(v, "TV", "TOT")
        if not s.empty:
            fig_vol.add_trace(go.Scatter(x=s["date"], y=s["value"] / 1e6, name=cfg["nombre"],
                mode="lines", line={"color": cfg["color"], "width": 1.6},
                hovertemplate=f"{cfg['nombre']}<br>%{{x|%Y-%m-%d}}<br>$%{{y:,.2f}} B<extra></extra>"))
    # Línea TOTAL = suma de los tres venues por fecha (repo garantizado total).
    tv_all = df[(df.metric == "TV") & (df.segment == "TOT")
                & (df.venue.isin(list(VENUES)))]
    total = tv_all.groupby("date")["value"].sum().sort_index()
    if not total.empty:
        fig_vol.add_trace(go.Scatter(x=total.index, y=total.values / 1e6,
            name="Total (todos los venues)", mode="lines",
            line={"color": "#8c6bb1", "width": 2.4},
            hovertemplate="Total<br>%{x|%Y-%m-%d}<br>$%{y:,.2f} B<extra></extra>"))
    apply_standard_layout(fig_vol)
    fig_vol.update_layout(yaxis_title="Billones USD", hovermode="x unified",
                          legend={"orientation": "h", "y": -0.15})

    fig_rate = go.Figure()
    for v, cfg in VENUES.items():
        s = ser(v, "AR", "TOT")
        if not s.empty:
            fig_rate.add_trace(go.Scatter(x=s["date"], y=s["value"], name=cfg["nombre"],
                mode="lines", line={"color": cfg["color"], "width": 1.6},
                hovertemplate=f"{cfg['nombre']}<br>%{{x|%Y-%m-%d}}<br>%{{y:.2f}}%<extra></extra>"))
    apply_standard_layout(fig_rate)
    fig_rate.update_layout(yaxis_title="Tasa (%)", hovermode="x unified",
                           legend={"orientation": "h", "y": -0.15})

    fig_tenor = go.Figure()
    for seg, label, color in [("TOT", "Total", "#4c78a8"), ("OO", "Overnight & Open", "#72b7b2"),
                              ("LE30", "≤ 30 días", "#f2b701"), ("G30", "> 30 días", "#e45756")]:
        s = ser("DVP", "AR", seg)
        if not s.empty:
            fig_tenor.add_trace(go.Scatter(x=s["date"], y=s["value"], name=label, mode="lines",
                line={"color": color, "width": 1.5},
                hovertemplate=f"DVP {label}<br>%{{x|%Y-%m-%d}}<br>%{{y:.2f}}%<extra></extra>"))
    apply_standard_layout(fig_tenor)
    fig_tenor.update_layout(yaxis_title="Tasa DVP (%)", hovermode="x unified",
                            legend={"orientation": "h", "y": -0.15})

    fig_flow = go.Figure()
    tv, ov = ser("DVP", "TV", "TOT"), ser("DVP", "OV", "TOT")
    if not tv.empty:
        fig_flow.add_trace(go.Scatter(x=tv["date"], y=tv["value"] / 1e6, name="Negociado (flujo)",
            mode="lines", line={"color": "#4c78a8", "width": 1.5},
            hovertemplate="Negociado<br>%{x|%Y-%m-%d}<br>$%{y:,.2f} B<extra></extra>"))
    if not ov.empty:
        fig_flow.add_trace(go.Scatter(x=ov["date"], y=ov["value"] / 1e6, name="Vivo (saldo)",
            mode="lines", line={"color": "#e45756", "width": 1.5, "dash": "dot"},
            hovertemplate="Vivo<br>%{x|%Y-%m-%d}<br>$%{y:,.2f} B<extra></extra>"))
    apply_standard_layout(fig_flow)
    fig_flow.update_layout(yaxis_title="Billones USD", hovermode="x unified",
                           legend={"orientation": "h", "y": -0.15})

    for f in (fig_vol, fig_rate, fig_tenor, fig_flow):
        add_sp500_reference(f, periodo)
    return fig_vol, fig_rate, fig_tenor, fig_flow


# ==================================================================
# TAB 2 — Tasas y estrés
# ==================================================================
@callback(
    Output("rb-rates", "figure"), Output("rb-band", "figure"),
    Output("rb-stress", "figure"), Output("rb-vol-sofr", "figure"),
    Output("rb-kpi-sofr", "children"), Output("rb-kpi-p99", "children"),
    Output("rb-kpi-stress", "children"), Output("rb-kpi-vol", "children"),
    Input("rb-periodo", "value"),
)
def update_rates(periodo):
    df = _load(OFRReferenceRate, ["date", "rate", "stat", "value"], periodo)
    if df.empty:
        e = empty_figure("Sin datos — ejecuta: python run_pipeline.py ofr_rates --full")
        return e, e, e, e, "N/A", "N/A", "N/A", "N/A"

    def ser(rate, stat):
        s = df[(df.rate == rate) & (df.stat == stat)]
        return s.sort_values("date")

    fig_rates = go.Figure()
    for rate, cfg in REPO_RATES.items():
        s = ser(rate, "LEVEL")
        if not s.empty:
            fig_rates.add_trace(go.Scatter(x=s["date"], y=s["value"], name=cfg["nombre"],
                mode="lines", line={"color": cfg["color"], "width": 1.5},
                hovertemplate=f"{cfg['nombre']}<br>%{{x|%Y-%m-%d}}<br>%{{y:.2f}}%<extra></extra>"))
    apply_standard_layout(fig_rates)
    fig_rates.update_layout(yaxis_title="Tasa (%)", hovermode="x unified",
                            legend={"orientation": "h", "y": -0.15})

    fig_band = go.Figure()
    p99, p1, lvl = ser("SOFR", "P99"), ser("SOFR", "P1"), ser("SOFR", "LEVEL")
    if not p99.empty and not p1.empty:
        fig_band.add_trace(go.Scatter(x=p99["date"], y=p99["value"], name="P99", mode="lines",
            line={"width": 0, "color": "rgba(228,87,86,0)"},
            hovertemplate="P99: %{y:.2f}%<extra></extra>"))
        fig_band.add_trace(go.Scatter(x=p1["date"], y=p1["value"], name="Banda P1–P99",
            mode="lines", line={"width": 0, "color": "rgba(228,87,86,0)"},
            fill="tonexty", fillcolor="rgba(228,87,86,0.20)",
            hovertemplate="P1: %{y:.2f}%<extra></extra>"))
    if not lvl.empty:
        fig_band.add_trace(go.Scatter(x=lvl["date"], y=lvl["value"], name="SOFR (nivel)",
            mode="lines", line={"color": "#4c78a8", "width": 1.6},
            hovertemplate="SOFR: %{y:.2f}%<extra></extra>"))
    apply_standard_layout(fig_band)
    fig_band.update_layout(yaxis_title="Tasa (%)", hovermode="x unified",
                           legend={"orientation": "h", "y": -0.15})

    fig_stress = go.Figure()
    for rate, color in [("SOFR", "#4c78a8"), ("TGCR", "#e4a23b")]:
        lv = ser(rate, "LEVEL").set_index("date")["value"]
        p = ser(rate, "P99").set_index("date")["value"]
        if not lv.empty and not p.empty:
            spread = ((p - lv) * 100).dropna()
            fig_stress.add_trace(go.Scatter(x=spread.index, y=spread.values,
                name=f"{rate} (P99−nivel)", mode="lines", line={"color": color, "width": 1.3},
                hovertemplate=f"{rate}<br>%{{x|%Y-%m-%d}}<br>%{{y:.0f}} pb<extra></extra>"))
    apply_standard_layout(fig_stress)
    fig_stress.update_layout(yaxis_title="P99 − nivel (pb)", hovermode="x unified",
                             legend={"orientation": "h", "y": -0.15})

    fig_vol = go.Figure()
    vol = ser("SOFR", "VOLUME")
    if not vol.empty:
        fig_vol.add_trace(go.Scatter(x=vol["date"], y=vol["value"] / 1e6, name="Volumen SOFR",
            mode="lines", line={"color": "#72b7b2", "width": 1.4}, fill="tozeroy",
            fillcolor="rgba(114,183,178,0.15)",
            hovertemplate="%{x|%Y-%m-%d}<br>$%{y:,.2f} B<extra></extra>"))
    apply_standard_layout(fig_vol)
    fig_vol.update_layout(yaxis_title="Billones USD", hovermode="x unified", showlegend=False)

    for f in (fig_rates, fig_band, fig_stress, fig_vol):
        add_sp500_reference(f, periodo)

    def last(rate, stat):
        s = ser(rate, stat)
        return s["value"].iloc[-1] if not s.empty else None
    sofr, p99v, volv = last("SOFR", "LEVEL"), last("SOFR", "P99"), last("SOFR", "VOLUME")
    sofr_t = f"{sofr:.2f}%" if sofr is not None else "N/A"
    p99_t = f"{p99v:.2f}%" if p99v is not None else "N/A"
    if sofr is not None and p99v is not None:
        pb = (p99v - sofr) * 100
        color = "text-danger" if pb >= 20 else ("text-warning" if pb >= 8 else "text-success")
        stress_t = html.Span(f"{pb:+.0f} pb", className=color)
    else:
        stress_t = "N/A"
    vol_t = f"${volv / 1e6:,.2f} B" if volv is not None else "N/A"
    return fig_rates, fig_band, fig_stress, fig_vol, sofr_t, p99_t, stress_t, vol_t


# ==================================================================
# TAB 3 — Primary dealers
# ==================================================================
@callback(
    Output("rb-dealer-tot", "figure"), Output("rb-dealer-collat", "figure"),
    Output("rb-dealer-tenor", "figure"),
    Output("rb-kpi-repo", "children"), Output("rb-kpi-repo-d", "children"),
    Output("rb-kpi-rrepo", "children"), Output("rb-kpi-rrepo-d", "children"),
    Output("rb-kpi-peak", "children"),
    Input("rb-periodo", "value"),
)
def update_dealers(periodo):
    # Serie HISTÓRICA (2015–2021). Se carga completa y la ventana del selector de periodo
    # se ancla al PROPIO histórico de la serie (no a hoy), para que "zoomee" sobre 2015–2021
    # en vez de vaciar el gráfico.
    df = _load(OFRDealerFinancing, ["date", "flow", "collateral", "tenor", "value"], 0)
    if df.empty:
        e = empty_figure("Sin datos — ejecuta: python run_pipeline.py ofr_dealer --full")
        return e, e, e, "N/A", "", "N/A", "", "N/A"

    data_start, data_end = df["date"].min(), df["date"].max()
    if periodo and periodo > 0:
        win_start = max(data_start, data_end - pd.Timedelta(days=periodo))
    else:
        win_start = data_start
    dfw = df[df["date"] >= win_start]

    leaves = [c for c, _, _ in DEALER_COLLAT]

    def ser(flow, collateral, tenor):
        s = dfw[(dfw.flow == flow) & (dfw.collateral == collateral) & (dfw.tenor == tenor)]
        return s.sort_values("date")

    def total_recon(flow, source):
        # El total agregado de la OFR (TOT/TOT) tiene muchos huecos (queda None si falta
        # cualquier componente → solo 55/31 puntos). Reconstruimos el total sumando los
        # colaterales hoja por fecha → línea densa y continua (reverse repo llega a 2021).
        sub = source[(source.flow == flow) & (source.tenor == "TOT")
                     & (source.collateral.isin(leaves))]
        return sub.groupby("date")["value"].sum().sort_index()

    # Total repo vs reverse repo (reconstruido desde colaterales)
    fig_tot = go.Figure()
    for flow, name, color in [("REPO", "Repo (toma efectivo)", "#4c78a8"),
                              ("REVERSE_REPO", "Reverse repo (presta efectivo)", "#e4a23b")]:
        t = total_recon(flow, dfw)
        if not t.empty:
            fig_tot.add_trace(go.Scatter(x=t.index, y=t.values / 1e6, name=name, mode="lines",
                line={"color": color, "width": 1.6},
                hovertemplate=f"{name}<br>%{{x|%Y-%m-%d}}<br>$%{{y:,.2f}} B<extra></extra>"))
    apply_standard_layout(fig_tot)
    fig_tot.update_layout(yaxis_title="Billones USD", hovermode="x unified",
                          legend={"orientation": "h", "y": -0.15})

    # Composición del repo por colateral (área apilada, hojas)
    fig_collat = go.Figure()
    for col, label, color in DEALER_COLLAT:
        s = ser("REPO", col, "TOT")
        if not s.empty:
            fig_collat.add_trace(go.Scatter(x=s["date"], y=s["value"] / 1e6, name=label,
                mode="lines", line={"width": 0.5, "color": color}, stackgroup="one",
                hovertemplate=f"{label}<br>%{{x|%Y-%m-%d}}<br>$%{{y:,.2f}} B<extra></extra>"))
    apply_standard_layout(fig_collat)
    fig_collat.update_layout(yaxis_title="Billones USD", hovermode="x unified",
                             legend={"orientation": "h", "y": -0.2})

    # Repo por plazo
    fig_tenor = go.Figure()
    for ten, label, color in [("OO", "Overnight & Open", "#4c78a8"),
                              ("L30", "≤ 30 días", "#f2b701"), ("GE30", "> 30 días", "#e45756")]:
        s = ser("REPO", "TOT", ten)
        if not s.empty:
            fig_tenor.add_trace(go.Scatter(x=s["date"], y=s["value"] / 1e6, name=label,
                mode="lines", line={"width": 0.5, "color": color}, stackgroup="one",
                hovertemplate=f"{label}<br>%{{x|%Y-%m-%d}}<br>$%{{y:,.2f}} B<extra></extra>"))
    apply_standard_layout(fig_tenor)
    fig_tenor.update_layout(yaxis_title="Billones USD", hovermode="x unified",
                            legend={"orientation": "h", "y": -0.15})

    # S&P de referencia en los tres, alineado a la ventana de datos de dealers.
    for f in (fig_tot, fig_collat, fig_tenor):
        add_sp500_reference(f, start=win_start, end=data_end)

    # KPIs (sobre el histórico completo y el total reconstruido, para estabilidad)
    def last_row(flow):
        t = total_recon(flow, df)
        if t.empty:
            return "N/A", ""
        return f"${t.iloc[-1] / 1e6:,.2f} B", f"{t.index[-1]:%d-%m-%Y}"
    repo_v, repo_d = last_row("REPO")
    rrepo_v, rrepo_d = last_row("REVERSE_REPO")
    peak_series = total_recon("REPO", df)
    peak_t = f"${peak_series.max() / 1e6:,.2f} B" if not peak_series.empty else "N/A"

    return (fig_tot, fig_collat, fig_tenor,
            repo_v, repo_d, rrepo_v, rrepo_d, peak_t)
