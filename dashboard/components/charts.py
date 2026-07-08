# dashboard/components/charts.py
# Utilidades para gráficos Plotly con estilo consistente

import plotly.graph_objects as go


# Plantilla base para todos los gráficos del proyecto
CHART_LAYOUT = dict(
    template='plotly_dark',
    font={'family': 'system-ui, -apple-system, sans-serif'},
    title_x=0.5,
    legend={'orientation': 'h', 'y': -0.15},
    margin={'l': 60, 'r': 30, 't': 60, 'b': 60},
)


def apply_standard_layout(fig: go.Figure, title: str = None) -> go.Figure:
    """Aplica el estilo estándar del proyecto a cualquier gráfico Plotly."""
    fig.update_layout(**CHART_LAYOUT)
    if title:
        fig.update_layout(title_text=title)
    return fig


# Color neutro para la línea de referencia del S&P 500 (eje secundario): no choca
# con las paletas de series y se lee como "fondo de mercado".
SP500_REF_COLOR = "rgba(220,220,220,0.55)"


def add_sp500_reference(
    fig: go.Figure,
    periodo_dias: int = 0,
    name: str = "S&P 500 (dcho.)",
    color: str = SP500_REF_COLOR,
) -> go.Figure:
    """
    Superpone el S&P 500 (^GSPC) en un eje Y secundario (derecha) como referencia
    de bolsa, para comparar visualmente cualquier serie con el mercado.

    La línea se muestra/oculta haciendo clic en su nombre en la leyenda (comportamiento
    estándar de Plotly). `periodo_dias=0` usa todo el histórico; >0 filtra a esa ventana.

    Reutilizable desde cualquier página: `add_sp500_reference(fig, periodo_dias)`.
    Los imports pesados van dentro para no acoplar este módulo de estilo a la capa de datos.
    """
    import pandas as pd
    from sqlalchemy import select
    from db.engine import get_session
    from db.models.indices import MarketIndex

    with get_session() as session:
        stmt = (
            select(MarketIndex)
            .where(MarketIndex.index_symbol == "^GSPC")
            .order_by(MarketIndex.date)
        )
        rows = session.execute(stmt).scalars().all()

    if not rows:
        return fig

    df = pd.DataFrame([{"date": r.date, "close": r.close_price} for r in rows])
    df["date"] = pd.to_datetime(df["date"])
    if periodo_dias and periodo_dias > 0:
        limite = pd.Timestamp.now().normalize() - pd.Timedelta(days=periodo_dias)
        df = df[df["date"] >= limite]
    if df.empty:
        return fig

    fig.add_trace(go.Scatter(
        x=df["date"], y=df["close"], name=name, mode="lines",
        line={"color": color, "width": 1.3}, yaxis="y2",
        hovertemplate="<b>S&P 500</b><br>%{x|%Y-%m-%d}<br>%{y:,.0f}<extra></extra>",
    ))
    fig.update_layout(yaxis2={
        "title": "S&P 500", "overlaying": "y", "side": "right",
        "showgrid": False, "zeroline": False,
    })
    return fig


def empty_figure(message: str = "Sin datos disponibles") -> go.Figure:
    """Genera un gráfico vacío con un mensaje centrado."""
    fig = go.Figure()
    fig.update_layout(
        **CHART_LAYOUT,
        annotations=[{
            'text': message,
            'xref': 'paper', 'yref': 'paper',
            'x': 0.5, 'y': 0.5,
            'showarrow': False,
            'font': {'size': 16, 'color': 'gray'}
        }],
        xaxis={'visible': False},
        yaxis={'visible': False},
    )
    return fig
