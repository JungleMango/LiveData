import streamlit as st
import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from datetime import date

api_key = "beUiETWAQ7Ert13VnAd7qkiEqjT1GrFC"
base_url = "https://financialmodelingprep.com"

st.set_page_config(page_title="Portfolio Tracker", page_icon="📂", layout="wide")

st.title("📂 Portfolio Tracker")
st.caption("Track your positions, live prices, and P/L using FinancialModelingPrep.")


# ----------------------------#
#           HELPERS           #
# ----------------------------#

def divider():
    st.markdown(
        "<hr style='border: 0; border-top: 1px solid #ddd; margin: 20px 0;'>",
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=15)
def fetch_live_prices(tickers: list[str]) -> pd.DataFrame:
    """
    Fetch live quotes for a list of tickers from FMP.
    Returns a DataFrame indexed by symbol.
    """
    tickers = [t.strip().upper() for t in tickers if t.strip()]
    if not tickers:
        return pd.DataFrame()

    symbols = ",".join(tickers)
    url = f"{base_url}/stable/quote?symbol={symbols}&apikey={api_key}"

    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return pd.DataFrame()

        data = resp.json()

        # FMP returns either a list or a dict with 'data'
        if isinstance(data, dict) and "data" in data:
            data = data["data"]

        df = pd.DataFrame(data)
        if df.empty:
            return df

        # Normalize column names a bit
        # Expecting at least: symbol, price, change, changesPercentage, etc.
        if "symbol" not in df.columns:
            return pd.DataFrame()

        df["symbol"] = df["symbol"].str.upper()
        df = df.set_index("symbol")

        return df

    except Exception:
        return pd.DataFrame()


# ----------------------------#
#      PORTFOLIO EDITOR       #
# ----------------------------#

st.subheader("📋 Your Positions")

# Initialize portfolio in session_state
if "portfolio_df" not in st.session_state:
    # Example starter row – you can clear or change this
    st.session_state["portfolio_df"] = pd.DataFrame(
        [
            {"Ticker": "XAUUSD", "Shares": 1.0, "Avg Cost": 4000.0},
        ]
    )

portfolio_df = st.data_editor(
    st.session_state["portfolio_df"],
    num_rows="dynamic",
    use_container_width=True,
    key="portfolio_editor",
    columns={
        "Ticker": st.column_config.TextColumn("Ticker", help="e.g. XAUUSD, AAPL, HHIS.TO"),
        "Shares": st.column_config.NumberColumn("Shares", min_value=0.0, step=1.0),
        "Avg Cost": st.column_config.NumberColumn("Average Cost ($)", min_value=0.0, step=0.01),
    },
)

# Save back to session_state
st.session_state["portfolio_df"] = portfolio_df

divider()

# ----------------------------#
#   LIVE PRICES + METRICS     #
# ----------------------------#

st.subheader("💹 Live Prices & P/L")

if portfolio_df.empty or portfolio_df["Ticker"].fillna("").str.strip().eq("").all():
    st.info("Add at least one row with a ticker, shares, and avg cost to see portfolio metrics.")
    st.stop()

# Clean tickers
portfolio_df = portfolio_df.copy()
portfolio_df["Ticker"] = portfolio_df["Ticker"].fillna("").str.upper().str.strip()
portfolio_df = portfolio_df[portfolio_df["Ticker"] != ""]

if portfolio_df.empty:
    st.info("Please enter at least one valid ticker.")
    st.stop()

tickers = portfolio_df["Ticker"].unique().tolist()

with st.spinner("Fetching live quotes from FMP..."):
    live_quotes = fetch_live_prices(tickers)

if live_quotes.empty:
    st.error("Could not fetch live prices. Check API key, symbols, or FMP status.")
    st.stop()

# Merge portfolio with live prices
merged = portfolio_df.merge(
    live_quotes,
    left_on="Ticker",
    right_index=True,
    how="left",
)

# Some FMP responses use 'price', some 'currentPrice', etc.
if "price" in merged.columns:
    merged["Current Price"] = merged["price"]
elif "currentPrice" in merged.columns:
    merged["Current Price"] = merged["currentPrice"]
else:
    merged["Current Price"] = np.nan

# Calculate metrics
merged["Position Value"] = merged["Shares"] * merged["Current Price"]
merged["Cost Basis"] = merged["Shares"] * merged["Avg Cost"]
merged["P/L $"] = merged["Position Value"] - merged["Cost Basis"]
merged["P/L %"] = np.where(
    merged["Cost Basis"] > 0,
    merged["P/L $"] / merged["Cost Basis"] * 100,
    np.nan,
)

# Totals
total_value = merged["Position Value"].sum()
total_cost = merged["Cost Basis"].sum()
total_pl = merged["P/L $"].sum()
total_pl_pct = (total_pl / total_cost * 100) if total_cost > 0 else np.nan

col_a, col_b, col_c, col_d = st.columns(4)
col_a.metric("Total Market Value", f"${total_value:,.2f}")
col_b.metric("Total Cost Basis", f"${total_cost:,.2f}")
col_c.metric("Total P/L", f"${total_pl:,.2f}")
col_d.metric("Total P/L %", f"{total_pl_pct:,.2f}%" if not np.isnan(total_pl_pct) else "N/A")

# Display detailed table
display_cols = [
    "Ticker",
    "Shares",
    "Avg Cost",
    "Current Price",
    "Position Value",
    "Cost Basis",
    "P/L $",
    "P/L %",
]

st.dataframe(
    merged[display_cols].sort_values("Position Value", ascending=False),
    use_container_width=True,
)

divider()

# ----------------------------#
#       SIMPLE VISUALS        #
# ----------------------------#

st.subheader("📊 Portfolio Breakdown")

# Pie/Bar chart by position value
value_by_ticker = merged.groupby("Ticker")["Position Value"].sum().sort_values(ascending=False)

if not value_by_ticker.empty:
    st.markdown("**Position Value by Ticker**")
    st.bar_chart(value_by_ticker)

# Optional: P/L bar chart
pl_by_ticker = merged.groupby("Ticker")["P/L $"].sum().sort_values()

if not pl_by_ticker.empty:
    st.markdown("**P/L by Ticker**")
    st.bar_chart(pl_by_ticker)
