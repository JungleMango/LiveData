import json
from pathlib import Path
from typing import Dict, List

import pandas as pd
import yfinance as yf
import streamlit as st
from urllib.parse import quote, unquote
import altair as alt

import streamlit as st

with st.sidebar:
    st.header("﹏𓊝﹏ Navigation")
    st.page_link("LiveData.py",             label="📊 Live Portfolio", icon="💼")
    st.page_link("pages/MarketOverview.py", label="🌍 Market Overview",  icon="🌎")


DATA_FILE = Path("portfolios.json")

# ---------- Helpers ----------
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
    tickers = sorted({t.strip().upper() for t in tickers if isinstance(t, str) and t.strip()})
    prices: Dict[str, float] = {}
    if not tickers:
        return prices
    # try intraday 1m
    try:
        df = yf.download(tickers=tickers, period="1d", interval="1m", group_by="ticker", progress=False, threads=True)
        if isinstance(df.columns, pd.MultiIndex):
            for t in tickers:
                try:
                    s = df[(t, "Close")].dropna()
                    if not s.empty:
                        prices[t] = float(s.iloc[-1])
                except Exception:
                    pass
        else:
            if "Close" in df.columns and not df["Close"].empty:
                prices[tickers[0]] = float(df["Close"].iloc[-1])
    except Exception:
        pass
    # fallback daily
    missing = [t for t in tickers if t not in prices]
    if missing:
        try:
            df = yf.download(tickers=missing, period="5d", interval="1d", group_by="ticker", progress=False, threads=True)
            if isinstance(df.columns, pd.MultiIndex):
                for t in missing:
                    try:
                        s = df[(t, "Close")].dropna()
                        if not s.empty:
                            prices[t] = float(s.iloc[-1])
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
    df["Live Price"] = pd.to_numeric(df["Ticker"].map(prices), errors="coerce")
    shares = df["Shares"].astype(float)
    avg    = df["Avg Cost"].astype(float)
    live   = df["Live Price"].astype(float)
    df["Cost Basis"]   = (shares * avg).round(2)
    df["Market Value"] = (shares * live).round(2)
    df["P/L $"]        = (df["Market Value"] - df["Cost Basis"]).round(2)
    df["P/L %"] = (
        df["P/L $"].div(df["Cost Basis"]).where(df["Cost Basis"].ne(0)).mul(100).fillna(0.0).round(2)
    )
    cols = ["Ticker", "Shares", "Avg Cost", "Live Price", "Cost Basis", "Market Value", "P/L $", "P/L %"]
    return df[cols]

def portfolio_totals(calc: pd.DataFrame) -> dict:
    invested = float(calc["Cost Basis"].sum(skipna=True))
    value = float(calc["Market Value"].sum(skipna=True))
    pl = float(calc["P/L $"].sum(skipna=True))
    growth = (pl / invested * 100) if invested else 0.0
    return {"Invested": invested, "Value": value, "P/L $": pl, "P/L %": round(growth, 2)}

def money(x): 
    return "" if pd.isna(x) else f"${x:,.2f}"

def colored_header_bg(text, bg_color="#0078D7", text_color="white", size=28, align="left", emoji=""):
    st.markdown(
        f"""
        <div style="
            background-color:{bg_color};
            color:{text_color};
            padding:10px 18px;
            border-radius:10px;
            text-align:{align};
            font-size:{size}px;
            font-weight:600;
            margin-top:0.5rem;
            margin-bottom:0.75rem;
        ">
            {emoji} {text}
        </div>
        """,
        unsafe_allow_html=True
    )
# ===== Charts helpers =====
@st.cache_data(ttl=300)
def fetch_history_bulk(tickers: list[str], period="6mo", interval="1d") -> dict[str, pd.Series]:
    """Return dict[ticker] -> Close price series (UTC index) for given period/interval."""
    tks = sorted({t for t in (tickers or []) if isinstance(t, str) and t.strip()})
    if not tks:
        return {}
    try:
        df = yf.download(
            tickers=tks, period=period, interval=interval,
            group_by="ticker", progress=False, threads=True
        )
    except Exception:
        return {}

    out: dict[str, pd.Series] = {}
    if isinstance(df.columns, pd.MultiIndex):
        # Multiple tickers
        for t in tks:
            try:
                s = df[(t, "Close")].dropna()
                if not s.empty:
                    out[t] = s
            except Exception:
                pass
    else:
        # Single ticker
        if "Close" in df.columns and not df["Close"].empty:
            out[tks[0]] = df["Close"].dropna()

    return out

def build_portfolio_history(holdings_df: pd.DataFrame, period="6mo", interval="1d") -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns:
      hist_df: DataFrame with columns ["Date","Portfolio Value","Growth %"]
      weights_df: DataFrame with columns ["Ticker","Market Value"] (latest)
    Assumes constant share counts over the period (no cash flows modeled).
    """
    df = holdings_df.copy()
    if df is None or df.empty:
        return (pd.DataFrame(columns=["Date", "Portfolio Value", "Growth %"]),
                pd.DataFrame(columns=["Ticker", "Market Value"]))

    # Clean & prep
    df["Ticker"] = df["Ticker"].astype(str).str.upper().str.strip()
    df["Shares"] = pd.to_numeric(df["Shares"], errors="coerce").fillna(0.0).astype(float)

    tickers = [t for t in df["Ticker"] if t]
    price_dict = fetch_history_bulk(tickers, period=period, interval=interval)

    if not price_dict:
        return (pd.DataFrame(columns=["Date", "Portfolio Value", "Growth %"]),
                pd.DataFrame(columns=["Ticker", "Market Value"]))

    # Align all series by date
    all_series = []
    for _, row in df.iterrows():
        t, sh = row["Ticker"], row["Shares"]
        if t in price_dict and sh > 0:
            s = price_dict[t] * sh  # position value over time
            s.name = t
            all_series.append(s)

    if not all_series:
        return (pd.DataFrame(columns=["Date", "Portfolio Value", "Growth %"]),
                pd.DataFrame(columns=["Ticker", "Market Value"]))

    aligned = pd.concat(all_series, axis=1).fillna(method="ffill").dropna(how="all")
    aligned["Portfolio Value"] = aligned.sum(axis=1)

    # Growth % from first available total
    first_val = aligned["Portfolio Value"].dropna().iloc[0]
    if first_val and first_val > 0:
        aligned["Growth %"] = (aligned["Portfolio Value"] / first_val - 1.0) * 100.0
    else:
        aligned["Growth %"] = 0.0

    hist_df = aligned[["Portfolio Value", "Growth %"]].reset_index()
    hist_df.rename(columns={"index": "Date"}, inplace=True)

    # Weights = latest point
    latest_row = aligned.drop(columns=["Portfolio Value", "Growth %"], errors="ignore").iloc[-1]
    weights_df = latest_row.reset_index()
    weights_df.columns = ["Ticker", "Market Value"]
    weights_df = weights_df[weights_df["Market Value"] > 0].sort_values("Market Value", ascending=False)

    return hist_df, weights_df

def format_money_short(x: float) -> str:
    try:
        x = float(x)
    except Exception:
        return ""
    if x >= 1_000_000_000:
        return f"${x/1_000_000_000:.2f}B"
    if x >= 1_000_000:
        return f"${x/1_000_000:.2f}M"
    if x >= 1_000:
        return f"${x/1_000:.2f}K"
    return f"${x:,.0f}"


# ---------- Defaults / State ----------
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
DEFAULT_WATCHLIST = pd.DataFrame([{"Ticker": "MSFT"}, {"Ticker": "ETH-USD"}, {"Ticker": "SPY"}])

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

# ---------- Top bar ----------
colored_header_bg("📊 Multi-Portfolio Dashboard", "#0078D7", "white", 34, "center")
left, right = st.columns([3, 2], vertical_alignment="center")

with left:
    with st.popover("➕ Add Portfolio"):
        new_name = st.text_input("Portfolio name", placeholder="e.g., Growth (USD)")
        if st.button("Create"):
            name = new_name.strip()
            if not name:
                st.error("Please enter a name.")
            elif name in st.session_state["portfolios"]:
                st.warning("That portfolio already exists.")
            else:
                st.session_state["portfolios"][name] = pd.DataFrame(columns=["Ticker", "Shares", "Avg Cost"])
                st.success(f"Created: {name}")

with right:
    if st.button("🔄 Refresh Prices"):
        st.cache_data.clear()
        st.rerun()
    if st.button("💾 Save to portfolios.json"):
        blob = {
            "portfolios": {k: v.to_dict(orient="records") for k, v in st.session_state["portfolios"].items()},
            "watchlist": st.session_state["watchlist"].to_dict(orient="records"),
        }
        DATA_FILE.write_text(json.dumps(blob, indent=2))
        st.success("Saved.")

# ---------- Query param / active selection ----------
# read ?p=<portfolio_name> if provided
qp = st.query_params
requested = None
if "p" in qp:
    requested = unquote(qp.get("p"))

portfolio_names = list(st.session_state["portfolios"].keys())
if not portfolio_names:
    st.info("No portfolios yet. Add one from the top-left.")
    st.stop()

# keep selection in session_state
if "active_portfolio" not in st.session_state:
    st.session_state["active_portfolio"] = portfolio_names[0]
if requested and requested in portfolio_names:
    st.session_state["active_portfolio"] = requested

# ---------- Fetch prices (all at once) ----------
all_tickers = []
for df in st.session_state["portfolios"].values():
    all_tickers.extend(_normalize_holdings(df)["Ticker"].tolist())
if "watchlist" not in st.session_state:
    st.session_state["watchlist"] = DEFAULT_WATCHLIST.copy()
all_tickers.extend(st.session_state["watchlist"]["Ticker"].astype(str).str.upper().tolist())
prices = fetch_prices_bulk(all_tickers)

# ---------- 1) All Portfolios table (clickable) ----------
colored_header_bg("💼 All Portfolios", "#FFD700", "#222", 26)
summary_rows = []
for name, df in st.session_state["portfolios"].items():
    calc = compute_holdings(df, prices)
    t = portfolio_totals(calc)
    url = f"?p={quote(name)}"
    summary_rows.append({
        "Portfolio": name,
        "Invested": t["Invested"],
        "Market Value": t["Value"],
        "P/L $": t["P/L $"],
        "P/L %": t["P/L %"],
        "Open": f"[Open]({url})"
    })
summary_df = pd.DataFrame(summary_rows).sort_values("P/L %", ascending=False, ignore_index=True)

st.dataframe(
    summary_df.style.format({
        "Invested": money, "Market Value": money, "P/L $": money, "P/L %": "{:,.2f}%"
    }),
    use_container_width=True,
)

st.caption("Tip: Click **Open** to jump to that portfolio. The selection is also stored in the URL (?p=...).")

# ---------- Active portfolio (stable state + deep-link) ----------
portfolio_names = list(st.session_state["portfolios"].keys())

# 1) Initialize once
if "active_portfolio" not in st.session_state:
    st.session_state["active_portfolio"] = portfolio_names[0]

# 2) If URL has ?p=..., adopt it (only if different & valid)
qp = st.query_params.get("p")
if qp and qp in portfolio_names and qp != st.session_state["active_portfolio"]:
    st.session_state["active_portfolio"] = qp

# 3) Radio behaves like tabs; on change, update URL (no other code overwrites it)
def _on_pick_change():
    picked = st.session_state["_portfolio_picker"]
    st.session_state["active_portfolio"] = picked
    st.query_params.update({"p": picked})  # keep deep-link in sync

colored_header_bg("📂 Portfolios", "#FF6F61", "white", 26)
picked_index = portfolio_names.index(st.session_state["active_portfolio"])
st.radio(
    "Select a portfolio",
    options=portfolio_names,
    index=picked_index,
    horizontal=True,
    label_visibility="collapsed",
    key="_portfolio_picker",
    on_change=_on_pick_change,
)

active = st.session_state["active_portfolio"]


# ---------- 3) Selected portfolio editor + breakdown ----------
df_edit = st.data_editor(
    _normalize_holdings(st.session_state["portfolios"][active]),
    num_rows="dynamic",
    use_container_width=True,
    key=f"editor_{active}",
    column_config={
        "Ticker": st.column_config.TextColumn(help="e.g., AAPL, NVDA, BTC-USD"),
        "Shares": st.column_config.NumberColumn(step=1, help="Number of shares/units"),
        "Avg Cost": st.column_config.NumberColumn(format="%.4f", help="Average cost per share/unit"),
    },
)
st.session_state["portfolios"][active] = _normalize_holdings(df_edit)

calc = compute_holdings(st.session_state["portfolios"][active], prices)
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

# ===== Charts under the selected portfolio =====
colored_header_bg("📈 Portfolio Charts", "#1E293B", "white", 24, emoji="📊")

# Choose history window
c_hist1, c_hist2 = st.columns([2, 1])
with c_hist2:
    period = st.selectbox("History window", ["1mo", "3mo", "6mo", "1y", "2y", "5y"], index=2)
    interval = "1d" if period not in ("1mo",) else "60m"  # finer granularity for short window

# Build history using the edited holdings of the ACTIVE portfolio (constant shares)
hist_df, weights_df = build_portfolio_history(st.session_state["portfolios"][active], period=period, interval=interval)

if hist_df.empty:
    st.info("No historical data available to chart yet for this portfolio.")
else:
    # --- Value line chart ---
    value_chart = (
        alt.Chart(hist_df)
        .mark_line()
        .encode(
            x=alt.X("Date:T", title="Date"),
            y=alt.Y("Portfolio Value:Q", title="Portfolio Value", axis=alt.Axis(format="~s")),
            tooltip=[
                alt.Tooltip("Date:T", title="Date"),
                alt.Tooltip("Portfolio Value:Q", title="Value", format=",.2f"),
                alt.Tooltip("Growth %:Q", title="Growth %", format=",.2f"),
            ],
        )
        .properties(height=300)
        .interactive()
    )

    # --- Growth % line chart ---
    growth_chart = (
        alt.Chart(hist_df)
        .mark_line()
        .encode(
            x=alt.X("Date:T", title="Date"),
            y=alt.Y("Growth %:Q", title="Growth %", axis=alt.Axis(format=",.0f")),
            tooltip=[
                alt.Tooltip("Date:T", title="Date"),
                alt.Tooltip("Growth %:Q", title="Growth %", format=",.2f"),
                alt.Tooltip("Portfolio Value:Q", title="Value", format=",.2f"),
            ],
        )
        .properties(height=300)
        .interactive()
    )

    st.altair_chart(value_chart, use_container_width=True)
    st.altair_chart(growth_chart, use_container_width=True)

# --- Weights donut ---
if not weights_df.empty:
    weights_df["Percent"] = weights_df["Market Value"] / weights_df["Market Value"].sum() * 100.0
    donut = (
        alt.Chart(weights_df)
        .mark_arc(innerRadius=70)  # donut
        .encode(
            theta=alt.Theta("Percent:Q"),
            color=alt.Color("Ticker:N", legend=alt.Legend(title="Ticker")),
            tooltip=[
                alt.Tooltip("Ticker:N"),
                alt.Tooltip("Market Value:Q", title="Value", format=",.2f"),
                alt.Tooltip("Percent:Q", title="Weight %", format=",.2f"),
            ],
        )
        .properties(height=320)
    )
    # Center label with total value
    center_text = alt.Chart(pd.DataFrame({
        "label": [format_money_short(hist_df["Portfolio Value"].iloc[-1])],
        "x": [0], "y": [0]
    })).mark_text(fontSize=16, fontWeight="bold").encode(text="label:N")

    colored_header_bg("Portfolio Weightage", "#111827", "white", 22)
    st.altair_chart(donut, use_container_width=True)
else:
    st.info("Weights are unavailable (no priced holdings).")


# ---------- 4) Watchlist ----------
colored_header_bg("👀 Watchlist", "#8A2BE2", "white", 26)
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

watch = st.session_state["watchlist"].copy()
watch["Ticker"] = watch["Ticker"].astype(str).str.upper().str.strip()
watch["Live Price"] = watch["Ticker"].map(prices)

@st.cache_data(ttl=60)
def day_change(tickers: List[str]) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame(columns=["Ticker", "Daily Change %"])
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
                        rows.append({"Ticker": t, "Daily Change %": round((last_close/prev_close - 1)*100, 2)})
                except Exception:
                    pass
        else:
            d = df.dropna()
            if len(d) >= 2:
                prev_close = float(d["Close"].iloc[-2])
                last_close = float(d["Close"].iloc[-1])
                rows.append({"Ticker": tickers[0], "Daily Change %": round((last_close/prev_close - 1)*100, 2)})
        return pd.DataFrame(rows)
    except Exception:
        return pd.DataFrame(columns=["Ticker", "Daily Change %"])

wl_changes = day_change([t for t in watch["Ticker"] if t])
watch = watch.merge(wl_changes, on="Ticker", how="left")

st.dataframe(
    watch.style.format({"Live Price": "${:,.4f}", "Daily Change %": "{:,.2f}%"}),
    use_container_width=True,
)
