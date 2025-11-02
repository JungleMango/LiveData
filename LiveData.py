import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import timezone

st.set_page_config(page_title="Portfolio Dashboard", page_icon="📊", layout="wide")

# ---------- Helpers ----------
@st.cache_data(ttl=60)
def fetch_prices(tickers: list[str]) -> dict:
    """Return last close/price for each ticker; ignores empties & failures."""
    prices = {}
    for t in tickers:
        t = t.strip().upper()
        if not t:
            continue
        try:
            hist = yf.Ticker(t).history(period="1d", interval="1m")
            if hist is None or hist.empty:
                # fallback to daily if intraday missing
                hist = yf.Ticker(t).history(period="5d", interval="1d")
            if hist is not None and not hist.empty:
                prices[t] = float(hist["Close"].iloc[-1])
        except Exception:
            pass
    return prices

def compute_pnl(df: pd.DataFrame, prices: dict, base_currency: str = "USD") -> pd.DataFrame:
    df = df.copy()
    df["Ticker"] = df["Ticker"].str.upper().str.strip()
    df["Shares"] = pd.to_numeric(df["Shares"], errors="coerce").fillna(0.0)
    df["Avg Cost"] = pd.to_numeric(df["Avg Cost"], errors="coerce").fillna(0.0)

    df["Live Price"] = df["Ticker"].map(prices).fillna(pd.NA)
    df["Cost Basis"] = (df["Shares"] * df["Avg Cost"]).round(2)
    df["Market Value"] = (df["Shares"] * df["Live Price"]).round(2)

    # P/L
    df["P/L $"] = (df["Market Value"] - df["Cost Basis"]).round(2)
    df["P/L %"] = ((df["P/L $"] / df["Cost Basis"]) * 100).replace([pd.NA, pd.NaT, float("inf"), -float("inf")], 0).round(2)

    # Order columns nicely
    cols = ["Ticker", "Shares", "Avg Cost", "Live Price", "Cost Basis", "Market Value", "P/L $", "P/L %"]
    return df[cols]

def format_money(x):
    return "" if pd.isna(x) else f"${x:,.2f}"

# ---------- Session State ----------
DEFAULT_ROWS = pd.DataFrame(
    [
        {"Ticker": "HHIS.TO", "Shares": 120, "Avg Cost": 13.56},
        {"Ticker": "NVDA", "Shares": 2, "Avg Cost": 950.00},
    ]
)

if "portfolio" not in st.session_state:
    st.session_state["portfolio"] = DEFAULT_ROWS.copy()

# ---------- Sidebar ----------
st.sidebar.header("Settings")
base_currency = st.sidebar.selectbox("Base currency (display only)", ["USD"], index=0)
refresh = st.sidebar.button("🔄 Refresh Prices")

st.sidebar.markdown("---")
st.sidebar.caption("💾 **Save / Load** your table")
uploaded = st.sidebar.file_uploader("Load CSV", type=["csv"])
if uploaded is not None:
    try:
        loaded = pd.read_csv(uploaded)
        # Minimal schema fix
        for col in ["Ticker", "Shares", "Avg Cost"]:
            if col not in loaded.columns:
                loaded[col] = pd.Series(dtype=float if col != "Ticker" else str)
        st.session_state["portfolio"] = loaded[["Ticker", "Shares", "Avg Cost"]]
        st.sidebar.success("Loaded CSV into the editor.")
    except Exception as e:
        st.sidebar.error(f"Couldn't load CSV: {e}")

csv_bytes = st.session_state["portfolio"].to_csv(index=False).encode("utf-8")
st.sidebar.download_button("⬇️ Download CSV", data=csv_bytes, file_name="portfolio.csv", mime="text/csv")

# ---------- Title & Help ----------
st.title("Live Portfolio Dashboard")
st.caption("Edit the table to add/remove holdings. Click **Refresh Prices** to update live quotes. (Prices cached ~60s)")

# ---------- Editable Table ----------
edited_df = st.data_editor(
    st.session_state["portfolio"],
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Ticker": st.column_config.TextColumn(help="e.g., AAPL, NVDA, BTC-USD"),
        "Shares": st.column_config.NumberColumn(step=1, help="Number of shares/units"),
        "Avg Cost": st.column_config.NumberColumn(format="%.4f", help="Average cost per share/unit"),
    },
    key="portfolio_editor"
)

# Persist edits
st.session_state["portfolio"] = edited_df

# ---------- Price Fetch & Calculations ----------
tickers = [t for t in edited_df["Ticker"].astype(str).str.upper().str.strip() if t]
prices = fetch_prices(tickers) if (refresh or True) else {}  # cached anyway

calc = compute_pnl(edited_df, prices, base_currency=base_currency)

# Totals
total_invested = calc["Cost Basis"].sum(skipna=True)
total_value = calc["Market Value"].sum(skipna=True)
total_pl = calc["P/L $"].sum(skipna=True)
total_pl_pct = (total_pl / total_invested * 100) if total_invested else 0.0

# ---------- KPI Row ----------
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Invested", format_money(total_invested))
c2.metric("Market Value", format_money(total_value))
c3.metric("P/L $", format_money(total_pl), delta=None)
c4.metric("P/L %", f"{total_pl_pct:,.2f}%")

# ---------- Results Table ----------
st.subheader("Holdings")
styled = (
    calc.style.format(
        {
            "Shares": "{:,.4f}",
            "Avg Cost": "${:,.4f}",
            "Live Price": "${:,.4f}",
            "Cost Basis": "${:,.2f}",
            "Market Value": "${:,.2f}",
            "P/L $": "${:,.2f}",
            "P/L %": "{:,.2f}%",
        }
    )
    .bar(subset=["P/L $"], color=["#f87171"], vmin=calc["P/L $"].min(), vmax=calc["P/L $"].max())  # red/green auto by range
    .hide(axis="index")
)
st.dataframe(calc, use_container_width=True)

# Optional: show styled as HTML (better bars), uncomment if you prefer:
# st.write(styled.to_html(), unsafe_allow_html=True)

st.caption("Tip: Add tickers like `BTC-USD` (Bitcoin), `ETH-USD` (Ethereum), US stocks (e.g., `AAPL`), ETFs (e.g., `QQQ`).")

# ---------- Footer ----------
st.markdown(
    "<small>Data via Yahoo Finance (`yfinance`). Not investment advice.</small>",
    unsafe_allow_html=True,
)
