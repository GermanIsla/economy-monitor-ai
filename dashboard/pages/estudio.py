# dashboard/pages/estudio.py
# Página: Estudio Liquidez↔Bolsa — visor del análisis del espacio research/.
# Tres bloques: (A) scorecard de señales, (B) letras en circulación vs mercado
# (la lección nivel-vs-cambio), (C) perfil adelantado de NFCI y fed_soma.

import dash
from dash import html, dcc, callback, Input, Output
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd

from dashboard.components.charts import apply_standard_layout, empty_figure
from research.analysis import (
    build_weekly_frame, load_series, to_changes, lead_lag, rolling_corr, scan,
    run_riskoff, series_meta, transform_for, SERIES,
)

STRESS_PCTL = 0.90  # umbral de "estrés alto" (percentil 90 de SOFR−EFFR)

dash.register_page(
    __name__,
    path="/estudio",
    name="Estudio Liquidez",
    title="Economy Monitor | Estudio Liquidez↔Bolsa",
)

# Predictores del scorecard (crédito y VIX son precios → sin sesgo de revisión).
SCORECARD_PREDICTORS = [
    "credit", "vix", "nfci", "net_liquidity", "reserves",
    "curve", "repo_haircut", "bills_outstanding", "wti",
]
# Series cuyo perfil lead/lag (bloque C) y correlación móvil (bloque D) se dibujan.
DEEP_DIVE = ["nfci", "vix", "net_liquidity"]
ROLLING = ["nfci", "vix", "reserves"]
ROLL_WINDOW = 52  # semanas (~1 año)

# Colores consistentes por factor en toda la página.
FACTOR_COLORS = {
    "nfci": "#e45756", "vix": "#f58518", "net_liquidity": "#4c78a8",
    "reserves": "#72b7b2", "credit": "#b279a2", "curve": "#9d755d",
    "fed_soma": "#54a24b",
}

ASSET_LABEL = {"sp500": "S&P 500", "btc": "Bitcoin"}


# ------------------------------------------------------------------
# Layout
# ------------------------------------------------------------------
layout = dbc.Container([
    html.H2("Estudio: Liquidez ↔ Bolsa", className="mb-1"),
    html.P(
        "Qué series adelantan al mercado, a qué horizonte y con qué fiabilidad. "
        "Correlaciones del espacio de análisis research/ (rejilla semanal, "
        "alineadas por fecha de publicación).",
        className="text-muted mb-3",
    ),

    dbc.Row([
        dbc.Col([
            html.Label("Activo objetivo:", className="fw-bold me-2"),
            dcc.Dropdown(
                id="estudio-asset",
                options=[{"label": v, "value": k} for k, v in ASSET_LABEL.items()],
                value="sp500", clearable=False, style={"width": "220px"},
            ),
        ], width="auto"),
    ], className="mb-4"),
    html.Hr(),

    # --- Bloque A: Scorecard ---
    html.H4("A · Scorecard de señales", className="mb-1"),
    html.P(
        "Correlación alineada del cambio de cada factor con el retorno FUTURO del "
        "activo a 1/4/13/26 semanas. Positivo = el factor adelanta a favor del activo. "
        "«Estable» = mantiene el signo antes y después de 2020.",
        className="text-muted small mb-3",
    ),
    dbc.Card(dbc.CardBody(html.Div(id="estudio-scorecard")), className="mb-4"),

    # --- Bloque B: Letras en circulación vs mercado ---
    html.H4("B · Letras en circulación vs mercado", className="mb-1"),
    html.P(
        "El clásico espejismo de la tendencia: dos series que suben con los años se "
        "parecen a la vista (nivel), pero sus cambios semanales pueden no tener relación.",
        className="text-muted small mb-3",
    ),
    dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody(
            dcc.Graph(id="estudio-bills-chart", style={"height": "400px"})
        )), width=12, lg=8),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("Correlación con el mercado", className="text-muted mb-3"),
            html.Div(id="estudio-bills-stats"),
        ])), width=12, lg=4),
    ], className="mb-4"),

    # --- Bloque C: Perfil adelantado ---
    html.H4("C · Perfil adelantado — factores principales", className="mb-1"),
    html.P(
        "Correlación del factor con el retorno semanal del mercado según el desfase. "
        "A la derecha (k>0) el factor ADELANTA al mercado; el pico marca el retardo óptimo.",
        className="text-muted small mb-3",
    ),
    dbc.Card(dbc.CardBody(
        dcc.Graph(id="estudio-leadlag-chart", style={"height": "420px"})
    ), className="mb-4"),

    # --- Bloque D: Correlación móvil (regímenes) ---
    html.H4("D · Correlación móvil — regímenes en el tiempo", className="mb-1"),
    html.P(
        f"Correlación en ventana móvil de {ROLL_WINDOW} semanas entre el cambio de cada "
        "factor y el retorno del mercado. Muestra las «épocas»: tramos donde la relación "
        "es fuerte y otros donde se desacopla o cambia de signo.",
        className="text-muted small mb-3",
    ),
    dbc.Card(dbc.CardBody(
        dcc.Graph(id="estudio-rolling-chart", style={"height": "420px"})
    ), className="mb-4"),

    # --- Bloque E: Emisión de letras → RRP ---
    html.H4("E · Emisión de letras → RRP (la fontanería)", className="mb-1"),
    html.P(
        "Hipótesis: emitir letras drena el Reverse Repo (los fondos monetarios cambian "
        "efectivo del RRP por letras). Independiente del activo seleccionado.",
        className="text-muted small mb-3",
    ),
    dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody(
            dcc.Graph(id="estudio-billsrrp-chart", style={"height": "400px"})
        )), width=12, lg=8),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("Emisión neta ↔ ΔRRP", className="text-muted mb-2"),
            html.Div(id="estudio-billsrrp-note"),
        ])), width=12, lg=4),
    ], className="mb-4"),

    # --- Bloque F: Estrés de financiación (estudio de eventos) ---
    html.H4("F · Estrés de financiación — estudio de eventos", className="mb-1"),
    html.P(
        "Estrés = SOFR−EFFR (tasa repo garantizada menos interbancaria). Como es una "
        "variable episódica, no vale la correlación lineal: comparamos el retorno del "
        "mercado en semanas de estrés alto vs la media.",
        className="text-muted small mb-3",
    ),
    dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody(
            dcc.Graph(id="estudio-funding-ts", style={"height": "380px"})
        )), width=12, lg=7),
        dbc.Col(dbc.Card(dbc.CardBody(
            dcc.Graph(id="estudio-funding-bars", style={"height": "380px"})
        )), width=12, lg=5),
    ], className="mb-2"),
    dbc.Row([dbc.Col(html.Div(id="estudio-funding-note"), width=12)], className="mb-4"),

    # --- Bloque G: ¿batimos a comprar y mantener? ---
    html.H4("G · ¿Vamos por buen camino? Estrategia risk-off vs comprar-y-mantener",
            className="mb-1"),
    html.P(
        "Estrategia: largo en el activo SALVO cuando el VIX o el spread de crédito entran "
        "en su 15% más alto (umbral con solo datos del pasado) → a liquidez. La idea es "
        "esquivar los regímenes malos, no adivinar máximos.",
        className="text-muted small mb-3",
    ),
    dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody(
            dcc.Graph(id="estudio-riskoff-chart", style={"height": "420px"})
        )), width=12, lg=8),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("Estrategia vs Comprar-y-mantener", className="text-muted mb-2"),
            html.Div(id="estudio-riskoff-note"),
        ])), width=12, lg=4),
    ], className="mb-4"),

    dcc.Markdown(
        "*Avisos: el **NFCI se revisa a posteriori** (sesgo de anticipación) → su ventaja "
        "está sobrestimada; `credit` y `vix` son precios, sin ese sesgo. Signos de `curve`/"
        "`vix` provisionales. Correlaciones in-sample; retornos solapados inflan la "
        "significancia. Magnitudes modestas → señales de apoyo. Detalle en "
        "`research/research_log.md`.*",
        className="text-muted small",
    ),
], fluid=True)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _color(val, thr=0.05):
    if val is None or val != val:
        return "text-muted"
    if val > thr:
        return "text-success"
    if val < -thr:
        return "text-danger"
    return "text-muted"


def _scorecard_table(asset: str):
    df = scan(SCORECARD_PREDICTORS, asset)
    header = html.Thead(html.Tr([
        html.Th("Factor"), html.Th("1s"), html.Th("4s"),
        html.Th("13s"), html.Th("26s"), html.Th("Estable"),
    ]))
    body_rows = []
    for key, row in df.iterrows():
        label = SERIES.get(key, {}).get("label", key)
        cells = [html.Td(label)]
        for h in ["1w", "4w", "13w", "26w"]:
            v = row.get(h)
            txt = "—" if (v is None or v != v) else f"{v:+.2f}"
            cells.append(html.Td(txt, className=_color(v)))
        estable = bool(row.get("estable"))
        cells.append(html.Td("✓" if estable else "·",
                             className="text-success" if estable else "text-muted"))
        body_rows.append(html.Tr(cells))
    return dbc.Table([header, html.Tbody(body_rows)],
                     bordered=False, hover=True, striped=True, size="sm",
                     className="mb-0")


def _bills_overlay(asset: str):
    frame = build_weekly_frame(["bills_outstanding", asset])
    if frame.empty:
        return empty_figure("Sin datos"), None, None
    base = frame.iloc[0]
    norm = frame / base * 100.0
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=norm.index, y=norm["bills_outstanding"], name="Letras en circulación",
        mode="lines", line={"color": "#f7931a", "width": 1.8},
    ))
    fig.add_trace(go.Scatter(
        x=norm.index, y=norm[asset], name=ASSET_LABEL[asset],
        mode="lines", line={"color": "#4c78a8", "width": 1.8},
    ))
    apply_standard_layout(fig, None)
    fig.update_layout(yaxis_title="Base 100 = inicio", xaxis_title="",
                      hovermode="x unified", legend={"orientation": "h", "y": -0.15})
    # correlación niveles vs cambios
    lvl = frame["bills_outstanding"].corr(frame[asset])
    chg = frame["bills_outstanding"].diff().corr(frame[asset].pct_change())
    return fig, lvl, chg


def _leadlag_fig(asset: str):
    ret = None
    fig = go.Figure()
    any_data = False
    for key in DEEP_DIVE:
        frame = build_weekly_frame([key, asset])
        if frame.empty:
            continue
        pred = to_changes(frame[key], transform_for(key))
        lag = int(series_meta(key, "publish_lag_weeks", 0) or 0)
        if lag:
            pred = pred.shift(lag)
        direction = int(series_meta(key, "direction", 1) or 1)
        mkt_ret = frame[asset].pct_change()
        corr = lead_lag(pred, mkt_ret, max_lag=26) * direction
        if corr.dropna().empty:
            continue
        any_data = True
        fig.add_trace(go.Scatter(
            x=corr.index, y=corr.values,
            name=SERIES.get(key, {}).get("label", key),
            mode="lines", line={"color": FACTOR_COLORS.get(key), "width": 2},
        ))
    if not any_data:
        return empty_figure("Sin datos suficientes")
    fig.add_vline(x=0, line={"dash": "dot", "color": "rgba(255,255,255,0.35)", "width": 1})
    fig.add_hline(y=0, line={"dash": "dot", "color": "rgba(255,255,255,0.2)", "width": 1})
    apply_standard_layout(fig, None)
    fig.update_layout(
        xaxis_title="Desfase en semanas  (→ el factor adelanta al mercado)",
        yaxis_title="Correlación alineada",
        hovermode="x unified", legend={"orientation": "h", "y": -0.15},
    )
    return fig


def _rolling_fig(asset: str):
    fig = go.Figure()
    any_data = False
    for key in ROLLING:
        frame = build_weekly_frame([key, asset])
        if frame.empty:
            continue
        pred = to_changes(frame[key], transform_for(key))
        direction = int(series_meta(key, "direction", 1) or 1)
        rc = rolling_corr(pred, frame[asset].pct_change(), window=ROLL_WINDOW) * direction
        if rc.dropna().empty:
            continue
        any_data = True
        fig.add_trace(go.Scatter(
            x=rc.index, y=rc.values,
            name=SERIES.get(key, {}).get("label", key),
            mode="lines", line={"color": FACTOR_COLORS.get(key), "width": 1.6},
        ))
    if not any_data:
        return empty_figure("Sin datos suficientes")
    fig.add_hline(y=0, line={"dash": "dot", "color": "rgba(255,255,255,0.25)", "width": 1})
    apply_standard_layout(fig, None)
    fig.update_layout(
        yaxis_title=f"Correlación móvil ({ROLL_WINDOW}s)", xaxis_title="",
        yaxis_range=[-1, 1], hovermode="x unified",
        legend={"orientation": "h", "y": -0.15},
    )
    return fig


def _bills_rrp_fig():
    """Emisión neta de letras (Δ4s del stock) vs nivel del RRP. Devuelve (fig, corr)."""
    frame = build_weekly_frame(["bills_outstanding", "rrp"])
    if frame.empty:
        return empty_figure("Sin datos"), None
    net_iss = frame["bills_outstanding"].diff(4) / 1e6   # billones USD / 4 semanas
    rrp_lvl = frame["rrp"] / 1e6                          # billones USD
    era = frame.index >= "2021-01-01"
    corr = net_iss[era].corr((rrp_lvl.diff(4))[era])

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=net_iss.index, y=net_iss.values, name="Emisión neta letras (Δ4s)",
        marker_color="#f7931a", opacity=0.6, yaxis="y",
        hovertemplate="Emisión 4s: %{y:+.2f} B USD<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=rrp_lvl.index, y=rrp_lvl.values, name="RRP (nivel)",
        mode="lines", line={"color": "#4c78a8", "width": 2}, yaxis="y2",
        hovertemplate="RRP: %{y:.2f} B USD<extra></extra>",
    ))
    apply_standard_layout(fig, None)
    fig.update_layout(
        yaxis={"title": "Emisión neta 4s (B USD)"},
        yaxis2={"title": "RRP (B USD)", "overlaying": "y", "side": "right",
                "showgrid": False},
        xaxis={"title": "", "range": ["2021-01-01", None]},
        hovermode="x unified", legend={"orientation": "h", "y": -0.18},
    )
    return fig, corr


def _funding_event(asset):
    """Estudio de eventos del estrés de financiación. Devuelve (fig_ts, fig_bars, note)."""
    stress = load_series("funding_stress").resample("W-FRI").max()
    price = load_series(asset).resample("W-FRI").last()
    d = pd.concat({"stress": stress, "px": price}, axis=1, sort=True).dropna()
    if d.empty or len(d) < 30:
        return empty_figure("Sin datos"), empty_figure("Sin datos"), None

    d["now"] = d["px"].pct_change()
    for h in (1, 4, 13):
        d[f"f{h}"] = d["px"].shift(-h) / d["px"] - 1
    thr = d["stress"].quantile(STRESS_PCTL)
    hi = d["stress"] >= thr

    # --- Serie temporal: estrés (barras) + activo (línea, eje secundario) ---
    fig_ts = go.Figure()
    fig_ts.add_trace(go.Bar(
        x=d.index, y=d["stress"], name="Estrés (SOFR−EFFR)",
        marker_color="#e45756", opacity=0.6, yaxis="y",
        hovertemplate="Estrés: %{y:.2f} pp<extra></extra>",
    ))
    fig_ts.add_trace(go.Scatter(
        x=d.index, y=d["px"], name=ASSET_LABEL[asset],
        mode="lines", line={"color": "#4c78a8", "width": 1.6}, yaxis="y2",
    ))
    fig_ts.add_hline(y=thr, line={"dash": "dot", "color": "rgba(228,87,86,0.6)", "width": 1})
    apply_standard_layout(fig_ts, None)
    fig_ts.update_layout(
        yaxis={"title": "Estrés SOFR−EFFR (pp)"},
        yaxis2={"title": ASSET_LABEL[asset], "overlaying": "y", "side": "right", "showgrid": False},
        xaxis={"title": ""}, hovermode="x unified", legend={"orientation": "h", "y": -0.18},
    )

    # --- Barras: retorno medio base vs estrés por horizonte ---
    cats = ["Misma sem.", "+1 sem.", "+4 sem.", "+13 sem."]
    cols = ["now", "f1", "f4", "f13"]
    base = [d[c].mean() * 100 for c in cols]
    strs = [d.loc[hi, c].mean() * 100 for c in cols]
    fig_bars = go.Figure()
    fig_bars.add_trace(go.Bar(x=cats, y=base, name="Media general", marker_color="#4c78a8"))
    fig_bars.add_trace(go.Bar(x=cats, y=strs, name="Tras estrés alto", marker_color="#e45756"))
    fig_bars.add_hline(y=0, line={"color": "rgba(255,255,255,0.3)", "width": 1})
    apply_standard_layout(fig_bars, None)
    fig_bars.update_layout(
        barmode="group", yaxis_title=f"Retorno medio {ASSET_LABEL[asset]} (%)",
        xaxis_title="", legend={"orientation": "h", "y": -0.18},
    )

    n_ev = int(hi.sum())
    note = html.Div([
        html.P([html.B("Contemporáneo: "), "en semanas de estrés alto el mercado suele "
                "caer (los bancos venden para proteger reservas). ",
                html.B("Después: "), "tiende a rebotar (los picos marcan capitulaciones)."],
               className="small text-muted mb-2"),
        html.P(f"Umbral: percentil {int(STRESS_PCTL*100)} (≈{thr:.2f} pp). "
               f"{n_ev} semanas de estrés, ~pocos episodios (2018+) → interpretar con cautela.",
               className="small text-muted mb-0"),
    ])
    return fig_ts, fig_bars, note


def _riskoff(asset):
    """Bloque G: curva estrategia risk-off vs comprar-y-mantener. (fig, note)."""
    r = run_riskoff(asset, risk_keys=("vix", "credit"), q=0.85)
    if not r:
        return empty_figure("Sin datos"), None
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=r["eq_bh"].index, y=r["eq_bh"], name="Comprar y mantener",
        mode="lines", line={"color": "#8899a6", "width": 1.6},
    ))
    fig.add_trace(go.Scatter(
        x=r["eq_strat"].index, y=r["eq_strat"], name="Estrategia risk-off",
        mode="lines", line={"color": "#54a24b", "width": 2},
    ))
    apply_standard_layout(fig, None)
    fig.update_layout(
        yaxis={"title": "Crecimiento de 1€ (escala log)", "type": "log"},
        xaxis_title="", hovermode="x unified", legend={"orientation": "h", "y": -0.15},
    )

    s, b = r["strat"], r["bh"]

    def row(nombre, sv, bv, better):
        win = "text-success" if better else "text-muted"
        return html.Tr([
            html.Td(nombre, className="small"),
            html.Td(sv, className=f"small text-end {win}"),
            html.Td(bv, className="small text-end text-muted"),
        ])

    note = html.Div([
        dbc.Table([
            html.Thead(html.Tr([html.Th(""), html.Th("Estrat.", className="text-end small"),
                                html.Th("B&H", className="text-end small")])),
            html.Tbody([
                row("Retorno anual (CAGR)", f"{s['cagr']*100:+.1f}%", f"{b['cagr']*100:+.1f}%",
                    s['cagr'] > b['cagr']),
                row("Sharpe (retorno/riesgo)", f"{s['sharpe']:.2f}", f"{b['sharpe']:.2f}",
                    s['sharpe'] > b['sharpe']),
                row("Caída máxima", f"{s['maxdd']*100:.0f}%", f"{b['maxdd']*100:.0f}%",
                    s['maxdd'] > b['maxdd']),
            ]),
        ], borderless=True, size="sm", className="mb-2"),
        html.P(f"Invertido el {r['pct_invested']*100:.0f}% del tiempo. "
               "Mejor Sharpe y menor caída = mejor retorno ajustado al riesgo; el hueco "
               "de retorno absoluto se cierra con apalancamiento (siguiente fase).",
               className="small text-muted mb-0"),
    ])
    return fig, note


# ------------------------------------------------------------------
# Callback
# ------------------------------------------------------------------
@callback(
    Output("estudio-scorecard", "children"),
    Output("estudio-bills-chart", "figure"),
    Output("estudio-bills-stats", "children"),
    Output("estudio-leadlag-chart", "figure"),
    Output("estudio-rolling-chart", "figure"),
    Output("estudio-billsrrp-chart", "figure"),
    Output("estudio-billsrrp-note", "children"),
    Output("estudio-funding-ts", "figure"),
    Output("estudio-funding-bars", "figure"),
    Output("estudio-funding-note", "children"),
    Output("estudio-riskoff-chart", "figure"),
    Output("estudio-riskoff-note", "children"),
    Input("estudio-asset", "value"),
)
def update_estudio(asset):
    table = _scorecard_table(asset)
    bills_fig, lvl, chg = _bills_overlay(asset)

    def stat_block(titulo, val, nota):
        return html.Div([
            html.Div(titulo, className="small text-muted"),
            html.H3(f"{val:+.2f}" if val is not None and val == val else "—",
                    className=f"mb-0 {_color(val, 0.1)}"),
            html.Div(nota, className="small text-muted mb-3"),
        ])

    stats = html.Div([
        stat_block("Correlación de NIVELES", lvl,
                   "Lo que ve el ojo: tendencia compartida."),
        stat_block("Correlación de CAMBIOS", chg,
                   "Lo que importa para predecir: movimiento semana a semana."),
        html.Hr(),
        html.P("Si niveles ≫ cambios, el parecido es tendencia común, no relación "
               "predictiva.", className="small text-muted mb-0"),
    ])

    leadlag_fig = _leadlag_fig(asset)
    rolling_fig = _rolling_fig(asset)
    billsrrp_fig, iss_rrp_corr = _bills_rrp_fig()

    note = html.Div([
        html.H3(f"{iss_rrp_corr:+.2f}" if iss_rrp_corr is not None and iss_rrp_corr == iss_rrp_corr else "—",
                className=f"mb-0 {_color(iss_rrp_corr, 0.2)}"),
        html.Div("correlación 2021+ (era RRP)", className="small text-muted mb-3"),
        html.P("Negativa y fuerte = emitir letras drena el RRP. La fontanería funciona.",
               className="small text-muted"),
        html.Hr(),
        html.P("⚠️ El RRP está hoy ~vacío (≈0): este canal está agotado. La nueva emisión "
               "drenará reservas bancarias directamente.", className="small text-muted mb-0"),
    ])
    funding_ts, funding_bars, funding_note = _funding_event(asset)
    riskoff_fig, riskoff_note = _riskoff(asset)
    return (table, bills_fig, stats, leadlag_fig, rolling_fig, billsrrp_fig, note,
            funding_ts, funding_bars, funding_note, riskoff_fig, riskoff_note)
