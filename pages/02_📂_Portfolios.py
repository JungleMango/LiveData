# 02_📂_Portfolios.py
# Live Portfolio Tracker — Google Sheets persistence (same [sheets] secrets) + yfinance quotes

import re, json, math, time
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

SHEET_TAB_NAME = "Portfolio"  # Tab name in your Google Sheet
PORTFOLIO_HEADER = ["Ticker", "Shares", "Avg Cost", "Currency", "Notes", "Last Updated"]

# Subtle highlight on editable columns
st.markdown("""
<style>
[data-testid="stDataEditor"] table tr td:nth-child(-n+5),
[data-testid="stDataEditor"] table tr th:nth-child(-n+5) {
  background-color: rgba(30,144,255,0.06);
}
</style>
""", unsafe_allow_html=True)

# ============================
#     SHEETS AUTH (same as portfolio)
# ============================

def signature(df: pd.DataFrame) -> int:
    tickers = df["Ticker"].tolist() if "Ticker" in df.columns else []
    return hash(tuple(tickers))

def _assert_sheets_secrets():
    if "sheets" not in st.secrets:
        st.error("Missing [sheets] in secrets (App → Settings → Secrets or .streamlit/secrets.toml).")
        st.stop()
    s = st.secrets["sheets"]
    for k in ("sheet_id", "service_account"):
        if k not in s:
            st.error(f"Missing key in [sheets]: {k}")
            st.stop()

def sheets_configured() -> bool:
    try:
        s = st.secrets["sheets"]
        return bool(s.get("sheet_id")) and bool(s.get("service_account"))
    except Exception:
        return False

@st.cache_resource
def get_sheet_client():
    _assert_sheets_secrets()
    raw = st.secrets["sheets"]["service_account"]

    if isinstance(raw, dict):
        info = raw
    else:
        # Escape real newlines inside the private_key ONLY (common paste issue)
        def _escape_pk_newlines(s: str) -> str:
            return re.sub(
                r'("private_key"\s*:\s*")([^"]+?)(")',
                lambda m: m.group(1) + m.group(2).replace("\n", "\\n") + m.group(3),
                s,
                flags=re.S,
            )
        fixed = _escape_pk_newlines(raw)
        info = json.loads(fixed)

    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return gspread.authorize(creds)

def _open_or_create_portfolio_ws(client: gspread.Client, sheet_id: str, tab_name: str):
    sh = client.open_by_key(sheet_id)
    try:
        ws = sh.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=tab_name, rows=1000, cols=len(PORTFOLIO_HEADER))
        ws.update("A1", [PORTFOLIO_HEADER])
    return ws

# ============================
#     SHEETS I/O HELPERS
# ============================

def _normalize_portfolio_df(df: pd.DataFrame) -> pd.DataFrame:
    # Ensure required columns exist
    for col in PORTFOLIO_HEADER:
        if col not in df.columns:
            df[col] = None if col in ("Shares", "Avg Cost") else ""

    # Trim + types
    df["Ticker"]   = df["Ticker"].fillna("").astype(str).str.strip().str.upper()
    df["Currency"] = df["Currency"].fillna("").astype(str).str.strip().str.upper()
    df["Notes"]    = df["Notes"].fillna("").astype(str)
    df["Shares"]   = pd.to_numeric(df["Shares"], errors="coerce")
    df["Avg Cost"] = pd.to_numeric(df["Avg Cost"], errors="coerce")

    # Drop fully blank rows (no ticker)
    df = df[df["Ticker"] != ""].copy()

    # Canonical column order
    return df[PORTFOLIO_HEADER]

def get_sheet_snapshot() -> pd.DataFrame:
    """Read current tickers from the sheet (robust, normalized)."""
    try:
        client = get_sheet_client()
        ws = _open_or_create_worksheet(client, st.secrets["sheets"]["sheet_id"], SHEET_TAB_NAME)
        values = ws.get_all_values()
        if not values:
            return pd.DataFrame({"Ticker": []})
        header, *rows = values
        if "Ticker" not in header:
            tickers = [r[0] for r in rows if r]
            return normalize_watch_df(pd.DataFrame({"Ticker": tickers}))
        df = pd.DataFrame(rows, columns=header)
        return normalize_watch_df(df)
    except Exception:
        return pd.DataFrame({"Ticker": []})


def get_portfolio_snapshot() -> pd.DataFrame:
    """Read current portfolio rows from the sheet (robust & normalized)."""
    try:
        client = get_sheet_client()
        ws = _open_or_create_portfolio_ws(client, st.secrets["sheets"]["sheet_id"], SHEET_TAB_NAME)
        values = ws.get_all_values()
        if not values:
            return pd.DataFrame(columns=PORTFOLIO_HEADER)
        header, *rows = values
        if not header:
            return pd.DataFrame(columns=PORTFOLIO_HEADER)

        # Back-compat: if only "Ticker" exists, expand
        if header == ["Ticker"]:
            tickers = [r[0] for r in rows if r]
            return _normalize_portfolio_df(pd.DataFrame({"Ticker": tickers}))

        df = pd.DataFrame(rows, columns=header)
        return _normalize_portfolio_df(df)
    except Exception:
        return pd.DataFrame(columns=PORTFOLIO_HEADER)

def save_portfolio_to_sheet(df: pd.DataFrame, prevent_empty: bool = True) -> bool:
    """
    Safely write the entire portfolio table.
    - Skips saving if cleaned df is empty (prevents nuking the tab).
    - Overwrites the sheet with canonical header + rows.
    """
    clean = _normalize_portfolio_df(df)
    if prevent_empty and clean.empty:
        st.warning("Skipped save: portfolio is empty (won’t overwrite the sheet).")
        return False

    client = get_sheet_client()
    ws = _open_or_create_portfolio_ws(client, st.secrets["sheets"]["sheet_id"], SHEET_TAB_NAME)

    # Timestamp just before write
    ts = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M:%S UTC")
    if "Last Updated" in clean.columns:
        clean.loc[:, "Last Updated"] = ts

    # Replace NaN with blanks for Sheets
    out = clean.where(pd.notna(clean), "")
    data = [PORTFOLIO_HEADER] + out.values.tolist()

    ws.clear()
    ws.update(f"A1:{chr(ord('A') + len(PORTFOLIO_HEADER) - 1)}{len(data)}", data)
    return True

# ============================
#        QUOTE HELPERS
# ============================

@st.cache_data(ttl=45, show_spinner=False)
def fetch_quotes(tickers: List[str]) -> pd.DataFrame:
    """
    Batch fetch latest prices and day change for tickers using yfinance.
    Returns columns: Ticker, Price, Day %, Prev Close, Time
    """
    tickers = [t.strip().upper() for t in tickers if t and isinstance(t, str)]
    tickers = sorted(set(tickers))
    if not tickers:
        return pd.DataFrame(columns=["Ticker", "Price", "Day %", "Prev Close", "Time"])

    # Multi-ticker intraday history; fallback to single if needed
    try:
        hist = yf.download(
            tickers=tickers, period="1d", interval="1m",
            group_by="ticker", auto_adjust=False, progress=False
        )
    except Exception:
        hist = pd.DataFrame()

    quotes = []
    ts_now = pd.Timestamp.utcnow().isoformat()

    for t in tickers:
        price = None
        prev_close = None
        day_pct = None

        try:
            sub = hist[t] if isinstance(hist.columns, pd.MultiIndex) else hist
            if sub is not None and not sub.empty:
                last = sub.iloc[-1]
                price = float(last["Close"])

            # Previous close via fast_info
            fi = yf.Ticker(t).fast_info
            prev_close = fi.get("previous_close", None)
            prev_close = float(prev_close) if prev_close is not None else None

            if price is not None and prev_close not in (None, 0) and not (isinstance(prev_close, float) and math.isnan(prev_close)):
                day_pct = (price / prev_close - 1) * 100.0
        except Exception:
            pass

        quotes.append({
            "Ticker": t,
            "Price": price,
            "Day %": day_pct,
            "Prev Close": prev_close,
            "Time": ts_now,
        })

    return pd.DataFrame(quotes)

def fmt2(x, none=""):
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return none
        return f"{x:.2f}"
    except Exception:
        return none

# ============================
#            UI
# ============================

st.title("📂 Portfolios")

topA, topB, topC = st.columns([2,1,1])
with topA:
    st.caption("Edit holdings below. The first five columns are editable and persist to Google Sheets.")
with topB:
    auto_refresh = st.toggle("Auto-refresh", value=True, help="Refresh quotes periodically")
with topC:
    interval = st.selectbox("Refresh Interval (sec)", [15, 30, 45, 60], index=1)

# Periodic refresh without deprecated APIs
if auto_refresh:
    now = time.time()
    last = st.session_state.get("last_refresh", 0.0)
    if now - last >= interval:
        st.session_state["last_refresh"] = now
        st.rerun()

# Load snapshot from Sheets
base_df = get_portfolio_snapshot()
if base_df.empty:
    base_df = pd.DataFrame([{
        "Ticker": "QQQ", "Shares": 10, "Avg Cost": 420.0,
        "Currency": "USD", "Notes": "Sample", "Last Updated": ""
    }])

st.subheader("Holdings (editable)")
edited = st.data_editor(
    base_df,
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

ctrl1, ctrl2, ctrl3 = st.columns([1,1,6])
with ctrl1:
    if st.button("💾 Save to Sheet", type="primary", use_container_width=True):
        if save_portfolio_to_sheet(edited):
            st.success("Saved to Google Sheet ✅")
            st.rerun()
with ctrl2:
    if st.button("➕ Add Row", use_container_width=True):
        edited = pd.concat(
            [edited, pd.DataFrame([{
                "Ticker":"", "Shares":0.0, "Avg Cost":0.0, "Currency":"", "Notes":"", "Last Updated":""
            }])],
            ignore_index=True
        )

# Work on a cleaned copy for quotes/calcs (don’t persist yet)
work = _normalize_portfolio_df(edited)
if work.empty:
    st.info("Add at least one ticker to see live valuation.")
    st.stop()

# Live quotes
tickers = work["Ticker"].tolist()
qdf = fetch_quotes(tickers)
merged = work.merge(qdf, on="Ticker", how="left")

# Calculations
merged["Price"] = pd.to_numeric(merged["Price"], errors="coerce")
merged["Shares"] = pd.to_numeric(merged["Shares"], errors="coerce")
merged["Avg Cost"] = pd.to_numeric(merged["Avg Cost"], errors="coerce")

merged["Market Value"] = merged["Price"] * merged["Shares"]
merged["Cost Basis"]   = merged["Avg Cost"] * merged["Shares"]
merged["P/L $"]        = merged["Market Value"] - merged["Cost Basis"]
merged["P/L %"]        = (merged["P/L $"] / merged["Cost Basis"]) * 100

# Portfolio totals
total_mv = float(pd.to_numeric(merged["Market Value"], errors="coerce").sum())
total_cb = float(pd.to_numeric(merged["Cost Basis"], errors="coerce").sum())
total_pl = total_mv - total_cb
total_pl_pct = (total_pl / total_cb * 100) if total_cb else float("nan")

# Weights
merged["Weight %"] = (merged["Market Value"] / total_mv * 100) if total_mv else 0.0

st.subheader("Live Valuation")
view_cols = [
    "Ticker","Shares","Avg Cost","Price","Market Value","Cost Basis","P/L $","P/L %","Day %","Weight %"
]
show = merged[view_cols].copy()

# Formatting
money_cols = ["Avg Cost","Price","Market Value","Cost Basis","P/L $"]
pct_cols = ["P/L %","Day %","Weight %"]

for c in money_cols:
    show[c] = show[c].apply(lambda x: fmt2(x))
for c in pct_cols:
    show[c] = show[c].apply(lambda x: ("" if x is None or (isinstance(x,float) and math.isnan(x)) else f"{x:.2f}%"))

st.dataframe(show, use_container_width=True, hide_index=True)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Market Value", f"{fmt2(total_mv)}")
m2.metric("Total Cost Basis", f"{fmt2(total_cb)}")
m3.metric("Total P/L $", f"{fmt2(total_pl)}")
m4.metric("Total P/L %", ("" if (isinstance(total_pl_pct,float) and math.isnan(total_pl_pct)) else f"{total_pl_pct:.2f}%"))

st.caption("Prices refresh using your interval. P/L uses latest fetched price against your Shares and Avg Cost.")







# ============================
#      SAVE / RELOAD / REFRESH
# ============================
c1, c2, c3 = st.columns([1,1,1])
with c1:
    if st.button("💾 Save Now"):
        if st.session_state["portfolio"].empty:
            st.warning("Won’t overwrite with an empty list. Add at least one ticker.")
        elif save_portfolio_to_sheet(st.session_state["portfolio"], prevent_empty=True):
            st.success("Saved to Google Sheets.")
            st.session_state["portfolio_saved_sig"] = signature(st.session_state["portfolio"])

with c2:
    if st.button("↩️ Reload from Sheet"):
        st.session_state["portfolio"] = get_sheet_snapshot()
        st.session_state["portfolio_saved_sig"] = signature(st.session_state["portfolio"])
        st.rerun()

with c3:
    if st.button("🔄 Refresh Data (clear cache)"):
        st.cache_data.clear()
        st.rerun()

# ============================
#          AUTOSAVE SAFE
# ============================
current_sig = signature(st.session_state["portfolio"])
last_saved_sig = st.session_state.get("portfolio_saved_sig")
if (
    sheets_configured()
    and last_saved_sig is not None
    and current_sig != last_saved_sig
    and not st.session_state["portfolio"].empty
    and time.time() - st.session_state["_wl_last_edit_ts"] > 1.5
):
    if save_portfolio_to_sheet(st.session_state["portfolio"], prevent_empty=True):
        st.toast("Autosaved to Google Sheets")
        st.session_state["portfolio_saved_sig"] = current_sig
