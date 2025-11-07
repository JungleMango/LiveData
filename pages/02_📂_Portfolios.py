# 02_📂_Portfolios.py
# Live Portfolio Tracker — Google Sheets persistence (same [sheets] secrets) + optimized quotes

import re, json, time, math, concurrent.futures as cf
from typing import List, Dict
import pandas as pd
import streamlit as st
import gspread
from google.oauth2 import service_account
import yfinance as yf

# ============================
#            CONFIG
# ============================
st.set_page_config(
    page_title="Portfolios",
    page_icon="📂",
    layout="wide",
    initial_sidebar_state="expanded",
)

SHEET_TAB_NAME = "Portfolio"
PORTFOLIO_HEADER = ["Ticker", "Shares", "Avg Cost", "Currency", "Notes", "Last Updated"]

st.markdown("""
<style>
[data-testid="stDataEditor"] table tr td:nth-child(-n+5),
[data-testid="stDataEditor"] table tr th:nth-child(-n+5) {
  background-color: rgba(30,144,255,0.06);
}
</style>
""", unsafe_allow_html=True)

# ============================
#        SECRETS / AUTH
# ============================
def _assert_sheets_secrets():
    if "sheets" not in st.secrets:
        st.error("Missing [sheets] in secrets (App → Settings → Secrets or .streamlit/secrets.toml).")
        st.stop()
    s = st.secrets["sheets"]
    for k in ("sheet_id", "service_account"):
        if k not in s:
            st.error(f"Missing key in [sheets]: {k}")
            st.stop()

@st.cache_resource(show_spinner=False)
def get_sheet_client() -> gspread.Client:
    _assert_sheets_secrets()
    raw = st.secrets["sheets"]["service_account"]
    if isinstance(raw, dict):
        info = raw
    else:
        def _escape_pk_newlines(s: str) -> str:
            return re.sub(
                r'("private_key"\s*:\s*")([^"]+?)(")',
                lambda m: m.group(1) + m.group(2).replace("\n", "\\n") + m.group(3),
                s, flags=re.S,
            )
        info = json.loads(_escape_pk_newlines(raw))
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return gspread.authorize(creds)

@st.cache_resource(show_spinner=False)
def get_portfolio_ws() -> gspread.Worksheet:
    gc = get_sheet_client()
    sh = gc.open_by_key(st.secrets["sheets"]["sheet_id"])
    try:
        ws = sh.worksheet(SHEET_TAB_NAME)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=SHEET_TAB_NAME, rows=1000, cols=len(PORTFOLIO_HEADER))
        ws.update("A1", [PORTFOLIO_HEADER])
    return ws

# ============================
#        SHEETS I/O
# ============================
def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Ensure columns
    for col in PORTFOLIO_HEADER:
        if col not in df.columns:
            df[col] = None if col in ("Shares", "Avg Cost") else ""

    # Types + cleanup
    df["Ticker"]   = df["Ticker"].fillna("").astype(str).str.strip().str.upper()
    df["Currency"] = df["Currency"].fillna("").astype(str).str.strip().str.upper()
    df["Notes"]    = df["Notes"].fillna("").astype(str)
    df["Shares"]   = pd.to_numeric(df["Shares"], errors="coerce")
    df["Avg Cost"] = pd.to_numeric(df["Avg Cost"], errors="coerce")

    df = df[df["Ticker"] != ""].copy()
    return df[PORTFOLIO_HEADER]

def read_portfolio() -> pd.DataFrame:
    try:
        ws = get_portfolio_ws()
        values = ws.get_all_values()
        if not values:
            return pd.DataFrame(columns=PORTFOLIO_HEADER)
        header, *rows = values
        if not header:
            return pd.DataFrame(columns=PORTFOLIO_HEADER)
        # Back-compat single-column sheets
        if header == ["Ticker"]:
            tickers = [r[0] for r in rows if r]
            return _normalize(pd.DataFrame({"Ticker": tickers}))
        df = pd.DataFrame(rows, columns=header)
        return _normalize(df)
    except Exception:
        return pd.DataFrame(columns=PORTFOLIO_HEADER)

def write_portfolio(df: pd.DataFrame, prevent_empty: bool = True) -> bool:
    clean = _normalize(df)
    if prevent_empty and clean.empty:
        st.warning("Skipped save: portfolio is empty (won’t overwrite the sheet).")
        return False

    ts = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M:%S UTC")
    clean.loc[:, "Last Updated"] = ts

    out = clean.where(pd.notna(clean), "")
    data = [PORTFOLIO_HEADER] + out.values.tolist()

    ws = get_portfolio_ws()
    ws.clear()
    ws.update(f"A1:{chr(ord('A') + len(PORTFOLIO_HEADER) - 1)}{len(data)}", data)
    return True

# ============================
#        QUOTES (optimized)
# ============================
def _threaded_prev_close(tickers: List[str]) -> Dict[str, float]:
    """Fetch previous_close via fast_info concurrently to cut latency for many tickers."""
    out: Dict[str, float] = {}
    def fetch_one(t: str):
        try:
            fi = yf.Ticker(t).fast_info
            pc = fi.get("previous_close", None)
            if pc is not None:
                out[t] = float(pc)
        except Exception:
            pass
    with cf.ThreadPoolExecutor(max_workers=min(8, max(2, len(tickers)))) as ex:
        list(ex.map(fetch_one, tickers))
    return out

@st.cache_data(ttl=45, show_spinner=False)
def fetch_quotes(tickers: List[str]) -> pd.DataFrame:
    """
    Returns: Ticker, Price, Day %, Prev Close, Time
    - Single yf.download call for last price
    - Threaded fast_info for previous_close
    """
    tickers = [t.strip().upper() for t in tickers if isinstance(t, str) and t.strip()]
    tickers = sorted(set(tickers))
    if not tickers:
        return pd.DataFrame(columns=["Ticker", "Price", "Day %", "Prev Close", "Time"])

    # Prices via single bulk download
    try:
        hist = yf.download(
            tickers=tickers, period="1d", interval="1m",
            group_by="ticker", auto_adjust=False, progress=False
        )
    except Exception:
        hist = pd.DataFrame()

    # Previous close via threaded fast_info
    prev_map = _threaded_prev_close(tickers)
    ts_now = pd.Timestamp.utcnow().isoformat()

    rows = []
    multi = isinstance(hist.columns, pd.MultiIndex)
    for t in tickers:
        price = None
        try:
            sub = hist[t] if multi else hist
            if sub is not None and not sub.empty:
                price = float(sub.iloc[-1]["Close"])
        except Exception:
            pass

        prev_close = prev_map.get(t)
        day_pct = None
        if price is not None and prev_close not in (None, 0) and not (isinstance(prev_close, float) and math.isnan(prev_close)):
            day_pct = (price / prev_close - 1) * 100.0

        rows.append({"Ticker": t, "Price": price, "Day %": day_pct, "Prev Close": prev_close, "Time": ts_now})

    return pd.DataFrame(rows)

# ============================
#              UI
# ============================
st.title("📂 Portfolios")

cA, cB, cC = st.columns([2,1,1])
with cA:
    st.caption("Edit holdings below. The first five columns are editable and persist to Google Sheets.")
with cB:
    auto_refresh = st.toggle("Auto-refresh", value=True, help="Refresh quotes periodically")
with cC:
    interval = st.selectbox("Refresh Interval (sec)", [15, 30, 45, 60], index=1)

# Modern periodic refresh
if auto_refresh:
    now = time.time()
    last = st.session_state.get("_portfolio_last_refresh", 0.0)
    if now - last >= interval:
        st.session_state["_portfolio_last_refresh"] = now
        st.rerun()

# Load + seed
df_sheet = read_portfolio()
if df_sheet.empty:
    df_sheet = pd.DataFrame([{
        "Ticker": "QQQ", "Shares": 10, "Avg Cost": 420.0,
        "Currency": "USD", "Notes": "Sample", "Last Updated": ""
    }])

st.subheader("Holdings (editable)")
edited = st.data_editor(
    df_sheet,
    num_rows="dynamic",
    use_container_width=True,
    hide_index=True,
    column_config={
        "Ticker": st.column_config.TextColumn(help="e.g., QQQ, NVDA, AAPL"),
        "Shares": st.column_config.NumberColumn(format="%.4f", help="Can be fractional"),
        "Avg Cost": st.column_config.NumberColumn(format="%.4f"),
        "Currency": st.column_config.TextColumn(help="USD/CAD/etc"),
        "Notes": st.column_config.TextColumn(),
        "Last Updated": st.column_config.TextColumn(disabled=True),
    },
)

b1, b2, _ = st.columns([1,1,6])
with b1:
    if st.button("💾 Save to Sheet", type="primary", use_container_width=True):
        if write_portfolio(edited):
            st.success("Saved to Google Sheet ✅")
            st.rerun()
with b2:
    if st.button("➕ Add Row", use_container_width=True):
        edited = pd.concat(
            [edited, pd.DataFrame([{
                "Ticker":"", "Shares":0.0, "Avg Cost":0.0, "Currency":"", "Notes":"", "Last Updated":""
            }])],
            ignore_index=True
        )

# ---------- Live Valuation ----------
work = _normalize(edited)
if work.empty:
    st.info("Add at least one ticker to see live valuation.")
    st.stop()

tickers = work["Ticker"].tolist()
qdf = fetch_quotes(tickers)
merged = work.merge(qdf, on="Ticker", how="left")

# Vectorized calcs
for col in ("Price", "Shares", "Avg Cost"):
    merged[col] = pd.to_numeric(merged[col], errors="coerce")

merged["Market Value"] = merged["Price"] * merged["Shares"]
merged["Cost Basis"]   = merged["Avg Cost"] * merged["Shares"]
merged["P/L $"]        = merged["Market Value"] - merged["Cost Basis"]
merged["P/L %"]        = (merged["P/L $"] / merged["Cost Basis"]) * 100

total_mv = float(pd.to_numeric(merged["Market Value"], errors="coerce").sum())
total_cb = float(pd.to_numeric(merged["Cost Basis"], errors="coerce").sum())
total_pl = total_mv - total_cb
total_pl_pct = (total_pl / total_cb * 100) if total_cb else float("nan")
merged["Weight %"] = (merged["Market Value"] / total_mv * 100) if total_mv else 0.0

st.subheader("Live Valuation")
view_cols = ["Ticker","Shares","Avg Cost","Price","Market Value","Cost Basis","P/L $","P/L %","Day %","Weight %"]
show = merged[view_cols].copy()

# Use column_config for formatting (faster than per-cell lambdas)
st.dataframe(
    show,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Shares":        st.column_config.NumberColumn(format="%.4f"),
        "Avg Cost":      st.column_config.NumberColumn(format="%.2f"),
        "Price":         st.column_config.NumberColumn(format="%.2f"),
        "Market Value":  st.column_config.NumberColumn(format="%.2f"),
        "Cost Basis":    st.column_config.NumberColumn(format="%.2f"),
        "P/L $":         st.column_config.NumberColumn(format="%.2f"),
        "P/L %":         st.column_config.NumberColumn(format="%.2f%%"),
        "Day %":         st.column_config.NumberColumn(format="%.2f%%"),
        "Weight %":      st.column_config.NumberColumn(format="%.2f%%"),
    }
)

m1, m2, m3, m4 = st.columns(4)
fmt2 = lambda x: "" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.2f}"
m1.metric("Total Market Value", fmt2(total_mv))
m2.metric("Total Cost Basis", fmt2(total_cb))
m3.metric("Total P/L $", fmt2(total_pl))
m4.metric("Total P/L %", ("" if (isinstance(total_pl_pct,float) and math.isnan(total_pl_pct)) else f"{total_pl_pct:.2f}%"))

st.caption("Prices refresh using your interval. P/L uses latest fetched price against your Shares and Avg Cost.")
