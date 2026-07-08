# dashboard/pages/indices.py
# Página: Índices Globales — precio de S&P 500 y Bitcoin
# Fuente: Yahoo Finance (pipeline `indices`). Modelo: MarketIndex.

import dash
from dash import html, dcc, callback, Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import select
from db.engine import get_session
from db.models.indices import MarketIndex
from dashboard.components.charts import apply_standard_layout, empty_figure

# --- Registro de página ---
dash.register_page(
    __name__,
    path="/indices",
    name="Índices Globales",
    title="Economy Monitor | Índices"
)

# Símbolos representados y su estilo. La clave es el index_symbol de la DB.
SERIES = {
    "^GSPC":   {"nombre": "S&P 500",       "color": "#4c78a8"},
    "BTC-USD": {"nombre": "Bitcoin (USD)", "color": "#f7931a"},
}

EXPLICACION = """
**¿Qué muestra esta página?**

El precio de dos activos de referencia del mercado global:

- 🔵 **S&P 500 (^GSPC):** El índice bursátil más seguido del mundo, que agrega las 500
  mayores empresas cotizadas de EE. UU. Es el termómetro del apetito por el riesgo en
  la renta variable «tradicional».

- 🟠 **Bitcoin (BTC-USD):** El activo digital de referencia. Cotiza 24/7 y suele
  comportarse como un activo de riesgo de alta beta, muy sensible a la liquidez global.

**El gráfico de comparación normalizada** rebasa ambos a base 100 en el inicio del
periodo, de modo que se aprecia la **rentabilidad relativa** (quién lo hace mejor) con
independencia de la enorme diferencia de escala entre sus precios. Es el primer paso
para estudiar cómo se relacionan estos activos entre sí y con el resto de datos del
monitor (liquidez, balances de bancos centrales, repo, etc.).
"""


# ------------------------------------------------------------------
# Layout
# ------------------------------------------------------------------
layout = dbc.Container([
    html.H2("Índices Globales", className="mb-1"),
    html.P(
        "Precio de los principales activos de referencia del mercado (Yahoo Finance).",
        className="text-muted mb-4"
    ),
    html.Hr(),

    # --- Filtro de periodo ---
    dbc.Row([
        dbc.Col([
            html.Label("Periodo:", className="fw-bold"),
            dcc.Dropdown(
                id="indices-periodo-filter",
                options=[
                    {"label": "1 año", "value": 365},
                    {"label": "3 años", "value": 1095},
                    {"label": "5 años", "value": 1825},
                    {"label": "10 años", "value": 3650},
                    {"label": "Todo el histórico", "value": 0},
                ],
                value=1825,
                clearable=False,
                style={"width": "220px"}
            ),
        ], width="auto"),
    ], className="mb-4"),

    # --- KPI cards ---
    dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("S&P 500", className="text-muted small mb-1"),
            html.H4(id="indices-kpi-sp500", className="mb-0", style={"color": "#4c78a8"}),
            html.Small(id="indices-kpi-sp500-chg", className="text-muted"),
        ])), width=6, md=6, className="mt-1"),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("Bitcoin (USD)", className="text-muted small mb-1"),
            html.H4(id="indices-kpi-btc", className="mb-0", style={"color": "#f7931a"}),
            html.Small(id="indices-kpi-btc-chg", className="text-muted"),
        ])), width=6, md=6, className="mt-1"),
    ], className="mb-4"),

    # --- S&P 500 ---
    dbc.Row([dbc.Col([
        html.H4("S&P 500", className="mb-2"),
        html.P("Nivel del índice (cierre diario).", className="text-muted small mb-3"),
        dbc.Card(dbc.CardBody(
            dcc.Graph(id="indices-sp500-chart", style={"height": "420px"})
        )),
    ], width=12)], className="mb-4"),

    # --- Bitcoin ---
    dbc.Row([dbc.Col([
        html.H4("Bitcoin", className="mb-2"),
        html.P("Precio spot en dólares (cierre diario).", className="text-muted small mb-3"),
        dbc.Card(dbc.CardBody(
            dcc.Graph(id="indices-btc-chart", style={"height": "420px"})
        )),
    ], width=12)], className="mb-4"),

    # --- Comparación normalizada ---
    dbc.Row([dbc.Col([
        html.H4("Comparación normalizada (base 100)", className="mb-2 mt-2"),
        html.P(
            "Ambos activos rebasados a 100 al inicio del periodo para comparar "
            "rentabilidad relativa con independencia de la escala de precios.",
            className="text-muted small mb-3"
        ),
        dbc.Card(dbc.CardBody(
            dcc.Graph(id="indices-compare-chart", style={"height": "440px"})
        )),
    ], width=12)], className="mb-4"),

    # --- Texto explicativo colapsable ---
    dbc.Row([dbc.Col([
        dbc.Button(
            "📖 ¿Qué significa esta página?",
            id="indices-collapse-btn",
            color="secondary", outline=True, size="sm", className="mb-2"
        ),
        dbc.Collapse(
            dbc.Card(dbc.CardBody(dcc.Markdown(EXPLICACION)),
                     className="mt-1 border-secondary"),
            id="indices-collapse",
            is_open=False,
        ),
    ], width=12)], className="mb-5"),

], fluid=True)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _load_df(periodo_dias: int) -> pd.DataFrame:
    """Carga market_indices en un DataFrame, filtrado por periodo."""
    with get_session() as session:
        stmt = select(MarketIndex).order_by(MarketIndex.date)
        results = session.execute(stmt).scalars().all()

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame([{
        "date": r.date,
        "symbol": r.index_symbol,
        "close": r.close_price,
    } for r in results])
    df["date"] = pd.to_datetime(df["date"])

    if periodo_dias and periodo_dias > 0:
        fecha_limite = pd.Timestamp.now().normalize() - pd.Timedelta(days=periodo_dias)
        df = df[df["date"] >= fecha_limite]

    return df


def _fmt_price(val: float) -> str:
    if val is None or val != val:
        return "N/A"
    if val >= 1000:
        return f"${val:,.0f}"
    return f"${val:,.2f}"


def _single_price_fig(df: pd.DataFrame, symbol: str, y_title: str) -> go.Figure:
    """Gráfico de línea de precio para un único símbolo."""
    cfg = SERIES[symbol]
    sub = df[df["symbol"] == symbol].sort_values("date")
    if sub.empty:
        return empty_figure(
            f"Sin datos — ejecuta: python run_pipeline.py indices --full"
        )

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sub["date"], y=sub["close"],
        name=cfg["nombre"], mode="lines",
        line={"color": cfg["color"], "width": 1.6},
        fill="tozeroy",
        fillcolor="rgba(76,120,168,0.12)" if symbol == "^GSPC"
                  else "rgba(247,147,26,0.12)",
        hovertemplate=f"<b>{cfg['nombre']}</b><br>%{{x|%Y-%m-%d}}<br>"
                      f"$%{{y:,.2f}}<extra></extra>",
    ))
    apply_standard_layout(fig, None)
    fig.update_layout(
        yaxis_title=y_title, xaxis_title="",
        hovermode="x unified", showlegend=False,
    )
    return fig


# ------------------------------------------------------------------
# Callbacks
# ------------------------------------------------------------------
@callback(
    Output("indices-sp500-chart", "figure"),
    Output("indices-btc-chart", "figure"),
    Output("indices-compare-chart", "figure"),
    Output("indices-kpi-sp500", "children"),
    Output("indices-kpi-sp500-chg", "children"),
    Output("indices-kpi-btc", "children"),
    Output("indices-kpi-btc-chg", "children"),
    Input("indices-periodo-filter", "value"),
)
def update_indices(periodo_dias):
    df = _load_df(periodo_dias)

    if df.empty:
        empty = empty_figure("Sin datos — ejecuta: python run_pipeline.py indices --full")
        return empty, empty, empty, "N/A", "", "N/A", ""

    # --- Gráficos individuales ---
    fig_sp = _single_price_fig(df, "^GSPC", "Nivel del índice")
    fig_btc = _single_price_fig(df, "BTC-USD", "USD")

    # --- Comparación normalizada (base 100) ---
    fig_cmp = go.Figure()
    for symbol, cfg in SERIES.items():
        sub = df[df["symbol"] == symbol].sort_values("date")
        if sub.empty:
            continue
        base = sub["close"].iloc[0]
        if not base or base != base:
            continue
        norm = sub["close"] / base * 100.0
        fig_cmp.add_trace(go.Scatter(
            x=sub["date"], y=norm,
            name=cfg["nombre"], mode="lines",
            line={"color": cfg["color"], "width": 1.8},
            hovertemplate=f"<b>{cfg['nombre']}</b><br>%{{x|%Y-%m-%d}}<br>"
                          f"%{{y:,.1f}} (base 100)<extra></extra>",
        ))
    fig_cmp.add_hline(y=100, line={"dash": "dot", "color": "rgba(255,255,255,0.25)", "width": 1})
    apply_standard_layout(fig_cmp, None)
    fig_cmp.update_layout(
        yaxis_title="Índice (base 100 = inicio del periodo)", xaxis_title="",
        hovermode="x unified",
        legend={"orientation": "h", "y": -0.15},
    )

    # --- KPIs: último precio + variación en el periodo mostrado ---
    def kpi(symbol):
        sub = df[df["symbol"] == symbol].sort_values("date")
        if sub.empty:
            return "N/A", ""
        last = sub["close"].iloc[-1]
        first = sub["close"].iloc[0]
        pct = (last / first - 1) * 100 if first else 0
        signo = "▲" if pct >= 0 else "▼"
        color = "text-success" if pct >= 0 else "text-danger"
        chg = html.Span(f"{signo} {pct:+.1f}% en el periodo", className=color)
        return _fmt_price(last), chg

    sp_val, sp_chg = kpi("^GSPC")
    btc_val, btc_chg = kpi("BTC-USD")

    return fig_sp, fig_btc, fig_cmp, sp_val, sp_chg, btc_val, btc_chg


@callback(
    Output("indices-collapse", "is_open"),
    Input("indices-collapse-btn", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_explicacion(n_clicks):
    return (n_clicks or 0) % 2 == 1
