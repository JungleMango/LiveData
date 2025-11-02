# multi_portfolio_dashboard.py
import json
from pathlib import Path
from typing import Dict, List

import pandas as pd
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Multi-Portfolio Dashboard", page_icon="📊", layout="wide")
st.title("📊 Multi-Portfolio Dashboard")

# =========================
# Helpers
# =========================
DATA_FILE = Path("portfolios.json")

def _normalize_holdings(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["Ticker", "Shares", "Avg Cost"])
    out = df.copy()
    for col in ["Ticker", "Shares", "Avg Cost"]:
        if col not in out.columns:
            out[col] = pd.NA
    out["Ticker"] = out["Ticker"].astype(str).str.upper().str.strip()
    out["Shares"] = pd.to_numeric(out["Shares"], errors="coerce").fillna(0.0)
    out["Avg Cost"] = pd.to_numeric(out["Avg Cost"], errors="coerce").fillna(0.0)
    return out[["Ticker", "Shares", "Avg Cost"]]

@st.cache_data(ttl=60)
def fetch_prices_bulk(tickers: List[str]) -> Dict[str, float]:
    """Fetch latest price per ticker (close of last bar)."""
    tickers = sorted({t.strip().upper() for t in tickers if t and isinstance(t, str)})
    prices: Dict[str, float] = {}
    if not tickers:
        return prices

    # Try 1-minute intraday for today; fallback to daily
    try:
        df = yf.download(tickers=tickers, period="1d", interval="1m", group_by="ticker", progress=False, threads=True)
        if isinstance(df.columns, pd.MultiIndex):
            for t in tickers:
                try:
                    close_series = df[(t, "Close")].dropna()
                    if not close_series.empty:
                        prices[t] = float(close_series.iloc[-1])
                except Exception:
                    pass
        else:
            # Single ticker
            if "Close" in df.columns and not df["Close"].empty:
                prices[tickers[0]] = float(df["Close"].iloc[-1])
    except Exception:
        pass

    # Fallback: daily
    missing = [t for t in tickers if t not in prices]
    if missing:
        try:
            df = yf.download(tickers=missing, period="5d", interval="1d", group_by="ticker", progress=False, threads=True)
            if isinstance(df.columns, pd.MultiIndex):
                for t in missing:
                    try:
                        close_series = df[(t, "Close")].dropna()
                        if not close_series.empty:
                            prices[t] = float(close_series.iloc[-1])
                    except Exception:
                        pass
            else:
                if "Close" in df.columns and not df["Close"].empty:
                    prices[missing[0]] = float(df["Close"].iloc[-1])
        except Exception:
            pass

    return prices

def compute_holdings(df: pd.DataFrame, prices: Dict[str, float]) -> pd.DataFrame:
    df = _normalize_holdings(df)
    df["Live Price"] = df["Ticker"].map(prices)
    df["Cost Basis"] = (df["Shares"] * df["Avg Cost"]).round(2)
    df["Market Value"] = (df["Shares"] * df["Live Price"]).round(2)
    df["P/L $"] = (df["Market Value"] - df["Cost Basis"]).round(2)
    with pd.option_context("mode.use_inf_as_na", True):
        df["P/L %"] = (df["P/L $"] / df["Cost Basis"] * 100).fillna(0.0).round(2)
    order = ["Ticker", "Shares", "Avg Cost", "Live Price", "Cost Basis", "Market Value", "P/L $", "P/L %"]
    return df[order]

def portfolio_totals(holdings_calc: pd.DataFrame) -> dict:
    invested = float(holdings_calc["Cost Basis"].sum(skipna=True))
    value = float(holdings_calc["Market Value"].sum(skipna=True))
    pl = float(holdings_calc["P/L $"].sum(skipna=True))
    growth = (pl / invested * 100) if invested else 0.0
    return {"Invested": invested, "Value": value, "P/L $": pl, "P/L %": round(growth, 2)}

def money(x): 
    return "" if pd.isna(x) else f"${x:,.2f}"

# =========================
# Session State / Defaults
# =========================
DEFAULT = {
    "Long-Term (USD)": pd.DataFrame([
        {"Ticker": "QQQ", "Shares": 10, "Avg Cost": 420.0},
        {"Ticker": "NVDA", "Shares": 2, "Avg Cost": 950.0},
        {"Ticker": "BTC-USD", "Shares": 0.05, "Avg Cost": 60000.0},
    ]),
    "TFSA (CAD)": pd.DataFrame([
        {"Ticker": "AAPL", "Shares": 5, "Avg Cost": 180.0},
        {"Ticker": "TSLA", "Shares": 2, "Avg Cost": 210.0},
    ]),
}
DEFAULT_WATCHLIST = pd.DataFrame(
    [{"Ticker": "MSFT"}, {"Ticker": "ETH-USD"}, {"Ticker": "SPY"}]
)

def load_state():
    if DATA_FILE.exists():
        try:
            blob = json.loads(DATA_FILE.read_text())
            portfolios = {}
            for name, rows in blob.get("portfolios", {}).items():
                portfolios[name] = _normalize_holdings(pd.DataFrame(rows))
            watch = pd.DataFrame(blob.get("watchlist", []))
            return portfolios or DEFAULT, (watch if not watch.empty else DEFAULT_WATCHLIST.copy())
        except Exception:
            pass
    return DEFAULT.copy(), DEFAULT_WATCHLIST.copy()

if "portfolios" not in st.session_state or "watchlist" not in st.session_state:
    st.session_state["portfolios"], st.session_state["watchlist"] = load_state()

# =========================
# Controls
# =========================
left, right = st.columns([3, 2])
with left:
    st.subheader("Portfolios")
    # Add/delete portfolios
    with st.popover("➕ Add Portfolio"):
        new_name = st.text_input("Portfolio name", value="", placeholder="e.g., Growth (USD)")
        if st.button("Create"):
            name = new_name.strip()
            if name:
                if name in st.session_state["portfolios"]:
                    st.warning("A portfolio with that name already exists.")
                else:
                    st.session_state["portfolios"][name] = pd.DataFrame(columns=["Ticker", "Shares", "Avg Cost"])
                    st.success(f"Created: {name}")
            else:
                st.error("Please enter a name.")

with right:
    st.subheader("Actions")
    refresh = st.button("🔄 Refresh Prices")
    if st.button("💾 Save to portfolios.json"):
        try:
            blob = {
                "portfolios": {k: v.to_dict(orient="records") for k, v in st.session_state["portfolios"].items()},
                "watchlist": st.session_state["watchlist"].to_dict(orient="records"),
            }
            DATA_FILE.write_text(json.dumps(blob, indent=2))
            st.success("Saved.")
        except Exception as e:
            st.error(f"Save failed: {e}")

# =========================
# Pricing & Calculations
# =========================
# Gather all tickers across portfolios + watchlist for one bulk fetch
all_tickers = []
for df in st.session_state["portfolios"].values():
    all_tickers.extend(_normalize_holdings(df)["Ticker"].tolist())
all_tickers.extend(st.session_state["watchlist"]["Ticker"].astype(str).str.upper().tolist())
prices = fetch_prices_bulk(all_tickers)  # cached 60s

# =========================
# 1) Summary table (top)
# =========================
st.markdown("### Portfolio Summary")
summary_rows = []
for name, df in st.session_state["portfolios"].items():
    calc = compute_holdings(df, prices)
    t = portfolio_totals(calc)
    summary_rows.append({
        "Portfolio": name,
        "Invested": t["Invested"],
        "Market Value": t["Value"],
        "P/L $": t["P/L $"],
        "P/L %": t["P/L %"],
    })

summary_df = pd.DataFrame(summary_rows).sort_values("P/L %", ascending=False, ignore_index=True)
st.dataframe(
    summary_df.style.format({
        "Invested": money, "Market Value": money, "P/L $": money, "P/L %": "{:,.2f}%"
    }),
    use_container_width=True,
)

# =========================
# 2) Per-portfolio breakdown (editable)
# =========================
st.markdown("### Portfolio Holdings (Editable)")
for name in sorted(st.session_state["portfolios"].keys()):
    st.markdown(f"#### {name}")
    # Editable table
    edited = st.data_editor(
        _normalize_holdings(st.session_state["portfolios"][name]),
        num_rows="dynamic",
        use_container_width=True,
        key=f"editor_{name}",
        column_config={
            "Ticker": st.column_config.TextColumn(help="e.g., AAPL, NVDA, BTC-USD"),
            "Shares": st.column_config.NumberColumn(step=1, help="Number of shares/units"),
            "Avg Cost": st.column_config.NumberColumn(format="%.4f", help="Average cost per share/unit"),
        },
    )
    # Persist edits
    st.session_state["portfolios"][name] = _normalize_holdings(edited)

    # Calculated view
    calc = compute_holdings(st.session_state["portfolios"][name], prices)
    tot = portfolio_totals(calc)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Invested", money(tot["Invested"]))
    k2.metric("Market Value", money(tot["Value"]))
    k3.metric("P/L $", money(tot["P/L $"]))
    k4.metric("P/L %", f"{tot['P/L %']:,.2f}%")

    st.dataframe(
        calc.style.format({
            "Shares": "{:,.4f}",
            "Avg Cost": "${:,.4f}",
            "Live Price": "${:,.4f}",
            "Cost Basis": "${:,.2f}",
            "Market Value": "${:,.2f}",
            "P/L $": "${:,.2f}",
            "P/L %": "{:,.2f}%",
        }),
        use_container_width=True,
    )
    st.divider()

# =========================
# 3) Watchlist
# =========================
st.markdown("### Watchlist (Editable)")
watch_edited = st.data_editor(
    st.session_state["watchlist"],
    num_rows="dynamic",
    use_container_width=True,
    key="watchlist_editor",
    column_config={
        "Ticker": st.column_config.TextColumn(help="Any Yahoo Finance symbol, e.g., MSFT, ETH-USD, XAUUSD=X"),
    },
)
st.session_state["watchlist"] = watch_edited

# Build watchlist table with prices and day change if available
watch = st.session_state["watchlist"].copy()
watch["Ticker"] = watch["Ticker"].astype(str).str.upper().str.strip()
watch["Live Price"] = watch["Ticker"].map(prices)

# Optional: get day % change via daily OHLC (small extra call; cached by fetch_prices_bulk for price only)
@st.cache_data(ttl=60)
def day_change(tickers: List[str]) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame(columns=["Ticker", "Change %"])
    try:
        df = yf.download(tickers=tickers, period="5d", interval="1d", group_by="ticker", progress=False, threads=True)
        rows = []
        if isinstance(df.columns, pd.MultiIndex):
            for t in tickers:
                try:
                    d = df[t].dropna()
                    if len(d) >= 2:
                        prev_close = float(d["Close"].iloc[-2])
                        last_close = float(d["Close"].iloc[-1])
                        chg = (last_close / prev_close - 1) * 100 if prev_close else 0.0
                        rows.append({"Ticker": t, "Change %": round(chg, 2)})
                except Exception:
                    pass
        else:
            # Single ticker
            d = df.dropna()
            if len(d) >= 2:
                prev_close = float(d["Close"].iloc[-2])
                last_close = float(d["Close"].iloc[-1])
                chg = (last_close / prev_close - 1) * 100 if prev_close else 0.0
                rows.append({"Ticker": tickers[0], "Change %": round(chg, 2)})
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame(columns=["Ticker", "Change %"])

wl_changes = day_change([t for t in watch["Ticker"] if t])
watch = watch.merge(wl_changes, on="Ticker", how="left")

st.dataframe(
    watch.style.format({"Live Price": "${:,.4f}", "Change %": "{:,.2f}%"}),
    use_container_width=True,
)
st.caption("Tip: Symbols can be stocks (AAPL), ETFs (QQQ), crypto (BTC-USD), FX/commodities (e.g., XAUUSD=X).")
