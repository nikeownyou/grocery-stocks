"""
Grocery Stocks
==============
Track staple grocery prices like stocks: daily movers, moving averages,
30-day highs/lows, and buy-the-dip signals — plus a basket index that
treats your whole grocery list like a portfolio.

WHAT YOU'LL LEARN FROM THIS FILE
- pandas rolling(): moving averages in one line
- groupby().apply(): computing per-ticker stats
- Merging stats back for an overview table
- Plotly multi-line charts (price + moving averages)
- A "basket index": summing one unit of each ticker per day
- st.form writing rows back to Google Sheets (same pattern as inventory)
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# 1. PAGE SETUP
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Grocery Stocks",
    page_icon="📈",
    layout="wide",
)

st.markdown(
    """
    <style>
    .app-header {
        background: linear-gradient(135deg, #0f2027 0%, #203a43 60%, #2c5364 100%);
        border-radius: 20px;
        padding: 2rem;
        color: white;
        margin-bottom: 1.5rem;
    }
    .app-header h1 { color: white !important; margin: 0; }
    .app-header p { color: #b8d4e3 !important; margin: 0.3rem 0 0 0; }
    .kpi-card {
        border-radius: 16px;
        padding: 1.2rem 1.4rem;
        color: white;
        box-shadow: 0 4px 14px rgba(0,0,0,0.12);
    }
    .kpi-card .kpi-label { font-size: 0.85rem; opacity: 0.9; }
    .kpi-card .kpi-value { font-size: 1.9rem; font-weight: 700; margin-top: 0.2rem; }
    .kpi-1 { background: linear-gradient(135deg, #11998e, #38ef7d); }
    .kpi-2 { background: linear-gradient(135deg, #667eea, #764ba2); }
    .kpi-3 { background: linear-gradient(135deg, #f093fb, #f5576c); }
    .kpi-4 { background: linear-gradient(135deg, #f6d365, #fda085); }
    .up { color: #e74c3c; font-weight: 600; }    /* prices up = bad, red */
    .down { color: #27ae60; font-weight: 600; }  /* prices down = good, green */
    </style>
    """,
    unsafe_allow_html=True,
)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# ---------------------------------------------------------------------------
# 2. DATA LOADING
# ---------------------------------------------------------------------------
@st.cache_resource
def get_worksheet():
    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPES,
    )
    client = gspread.authorize(creds)
    return client.open_by_key(st.secrets["sheet_id"]).sheet1


try:
    ws = get_worksheet()
    LIVE = True
except Exception:
    ws = None
    LIVE = False


@st.cache_data(ttl=600)
def load_data() -> pd.DataFrame:
    if LIVE:
        df = pd.DataFrame(ws.get_all_records())
    else:
        df = pd.read_csv("sample_data.csv")
        st.info("👀 Showing demo data — connect your Google Sheet (see README) for live prices.")

    df["Date"] = pd.to_datetime(df["Date"])
    df["Price"] = pd.to_numeric(df["Price"])
    return df.sort_values(["Ticker", "Date"]).reset_index(drop=True)


df = load_data()

# ---------------------------------------------------------------------------
# 3. STOCK-STYLE STATS PER TICKER
#    For each ticker: moving averages, % changes, 30-day high/low, signal.
# ---------------------------------------------------------------------------
def ticker_stats(g: pd.DataFrame) -> pd.Series:
    g = g.sort_values("Date")
    prices = g["Price"]
    cur, prev = prices.iloc[-1], prices.iloc[-2] if len(prices) > 1 else prices.iloc[-1]
    ma7 = prices.rolling(7, min_periods=1).mean().iloc[-1]
    ma30 = prices.rolling(30, min_periods=1).mean().iloc[-1]
    hi30, lo30 = prices.tail(30).max(), prices.tail(30).min()
    day_chg = (cur - prev) / prev * 100 if prev else 0
    w0 = prices.iloc[-1]
    w7 = prices.iloc[-8] if len(prices) > 7 else prices.iloc[0]
    week_chg = (w0 - w7) / w7 * 100 if w7 else 0

    if cur <= lo30 * 1.001:
        signal = "🟢 BUY — 30-day low"
    elif cur < ma7 * 0.97:
        signal = "🟢 BUY THE DIP"
    elif cur >= hi30 * 0.999:
        signal = "🔴 30-day high"
    else:
        signal = "➖ HOLD"

    return pd.Series({
        "Item": g["Item"].iloc[-1],
        "Unit": g["Unit"].iloc[-1],
        "Price": cur,
        "Day %": day_chg,
        "7d %": week_chg,
        "MA7": ma7,
        "MA30": ma30,
        "30d High": hi30,
        "30d Low": lo30,
        "Signal": signal,
    })


stats_rows = []
for ticker, g in df.groupby("Ticker"):
    s = ticker_stats(g)
    s["Ticker"] = ticker
    stats_rows.append(s)
stats = pd.DataFrame(stats_rows)

# ---------------------------------------------------------------------------
# 4. HEADER + KPIs
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div class="app-header">
        <h1>📈 Grocery Stocks</h1>
        <p>Your staples, traded like tickers. Buy the dip.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Basket index: one unit of every ticker, summed per day — the "portfolio"
basket = df.groupby("Date")["Price"].sum().reset_index(name="Basket")
basket_today = basket["Price"].iloc[-1]
basket_prev = basket["Price"].iloc[-2] if len(basket) > 1 else basket_today
basket_chg = (basket_today - basket_prev) / basket_prev * 100
buy_count = int(stats["Signal"].str.startswith("🟢").sum())

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
kpi1.markdown(
    f'<div class="kpi-card kpi-1"><div class="kpi-label">🧺 Basket index</div>'
    f'<div class="kpi-value">${basket_today:,.2f}</div></div>',
    unsafe_allow_html=True,
)
kpi2.markdown(
    f'<div class="kpi-card kpi-2"><div class="kpi-label">Basket day change</div>'
    f'<div class="kpi-value">{"+" if basket_chg >= 0 else ""}{basket_chg:.2f}%</div></div>',
    unsafe_allow_html=True,
)
kpi3.markdown(
    f'<div class="kpi-card kpi-3"><div class="kpi-label">🟢 Buy signals</div>'
    f'<div class="kpi-value">{buy_count}</div></div>',
    unsafe_allow_html=True,
)
kpi4.markdown(
    f'<div class="kpi-card kpi-4"><div class="kpi-label">Tickers tracked</div>'
    f'<div class="kpi-value">{len(stats)}</div></div>',
    unsafe_allow_html=True,
)

st.write("")

# ---------------------------------------------------------------------------
# 5. MARKET OVERVIEW — every ticker, one row each
# ---------------------------------------------------------------------------
st.subheader("📊 Market overview")

overview = stats.copy()
overview["Price"] = overview["Price"].map(lambda p: f"${p:.2f}")
overview["Day %"] = overview["Day %"].map(lambda x: f"{x:+.2f}%")
overview["7d %"] = overview["7d %"].map(lambda x: f"{x:+.2f}%")
overview["30d High"] = overview["30d High"].map(lambda p: f"${p:.2f}")
overview["30d Low"] = overview["30d Low"].map(lambda p: f"${p:.2f}")
cols = ["Ticker", "Item", "Unit", "Price", "Day %", "7d %", "30d High", "30d Low", "Signal"]
cols = [c for c in cols if c in overview.columns]
st.dataframe(overview[cols], use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# 6. TICKER DETAIL — price chart with moving averages
# ---------------------------------------------------------------------------
st.subheader("🔍 Ticker detail")
tickers = sorted(df["Ticker"].unique())
choice = st.selectbox("Ticker", options=tickers,
                      format_func=lambda t: f"{t} — {df[df['Ticker']==t]['Item'].iloc[-1]}")

g = df[df["Ticker"] == choice].sort_values("Date").copy()
g["MA7"] = g["Price"].rolling(7, min_periods=1).mean()
g["MA30"] = g["Price"].rolling(30, min_periods=1).mean()

fig = go.Figure()
fig.add_trace(go.Scatter(x=g["Date"], y=g["Price"], mode="lines+markers",
                         name="Price", line=dict(color="#2c5364", width=3)))
fig.add_trace(go.Scatter(x=g["Date"], y=g["MA7"], mode="lines",
                         name="7-day avg", line=dict(color="#f6d365", width=2, dash="dash")))
fig.add_trace(go.Scatter(x=g["Date"], y=g["MA30"], mode="lines",
                         name="30-day avg", line=dict(color="#f5576c", width=2, dash="dot")))
fig.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10),
                  title=f"{choice} — ${g['Price'].iloc[-1]:.2f} per {g['Unit'].iloc[-1]}",
                  yaxis_title="Price ($)", hovermode="x unified")
st.plotly_chart(fig, use_container_width=True)

s = stats[stats["Ticker"] == choice].iloc[0]
c1, c2, c3, c4 = st.columns(4)
c1.metric("30-day high", f"${s['30d High']:.2f}")
c2.metric("30-day low", f"${s['30d Low']:.2f}")
c3.metric("7-day avg", f"${s['MA7']:.2f}")
c4.metric("Signal", s["Signal"])

# ---------------------------------------------------------------------------
# 7. BASKET INDEX CHART
# ---------------------------------------------------------------------------
st.subheader("🧺 Basket index — your whole list as one portfolio")
fig_b = px.area(basket, x="Date", y="Basket", color_discrete_sequence=["#11998e"])
fig_b.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10),
                    yaxis_title="Total ($)")
st.plotly_chart(fig_b, use_container_width=True)

# ---------------------------------------------------------------------------
# 8. LOG A PRICE — manual entry (auto-tracking fills this daily too)
# ---------------------------------------------------------------------------
st.subheader("✏️ Log a price")
if not LIVE:
    st.info("🔒 Connect your Google Sheet to enable logging.")
else:
    with st.form("log_price", clear_on_submit=True):
        t = st.selectbox("Ticker", options=tickers)
        log_date = st.date_input("Date", value=pd.Timestamp.today().date())
        price = st.number_input("Price ($)", min_value=0.0, step=0.01, format="%.2f")
        note = st.text_input("Note (optional, e.g. sale)")
        submitted = st.form_submit_button("Log price", type="primary")
    if submitted:
        if price <= 0:
            st.error("Enter a price above $0.")
        else:
            item = df[df["Ticker"] == t]["Item"].iloc[-1]
            unit = df[df["Ticker"] == t]["Unit"].iloc[-1]
            ws.append_row([log_date.isoformat(), t, item, round(price, 2), unit,
                           "Atlantic Superstore", note.strip()],
                          value_input_option="USER_ENTERED")
            st.cache_data.clear()
            st.success(f"Logged **{t}** at ${price:.2f} ✓")
            st.rerun()

st.caption("Built with Streamlit 💛 — prices refresh daily from Atlantic Superstore.")
