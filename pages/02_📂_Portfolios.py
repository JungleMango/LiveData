# 03_💼_Portfolio_Tracker.py
# Portfolio Tracker — live valuation + P/L with Google Sheets persistence (same as watchlist)

import time
from typing import List, Dict
import math
import pandas as pd
import streamlit as st
import yfinance as yf
import gspread
from google.oauth2 import service_account

# ============================
#            CONFIG
# ============================
st.set_page_config(
    page_title="Portfolio Tracker",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---- Styling: highlight editable columns (Ticker, Shares, Avg Cost, Currency, Notes)
st.markdown("""
<style>
[data-testid="stDataEditor"] table tr td:nth-child(-n+5),
[data-testid="stDataEditor"] table tr th:nth-child(-n+5) {
  background-color: rgba(30,144,255,0.06);
}
</style>
""", unsafe_allow_html=True)

# Change this if you prefer a different tab name inside your Google Sheet
SHEET_TAB_NAME = "Portfolio"   # worksheet name inside the same Google Sheet as your Watchlist
# If your watchlist page loads credentials from st.secrets["gcp_service_account"], we’ll do the same:
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]

# ============================
#     GOOGLE SHEETS HELPERS
# ============================
@st.cache_resource(show_spinner=False)
def get_gspread_client():
    # Expecting the same secret you used on Watchlist:
    # st.secrets["gcp_service_account"] = {type, project_id, private_key_id, private_key, client_email, ...}
    creds = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES
    )
    return gspread.authorize(creds)

@st.cache_resource(show_spinner=False)
def get_worksheet(sheet_tab: str):
    gc = get_gspread_client()
    # Expect a sheet name in st.secrets just like your Watchlist page:
    # st.secrets["settings"]["sheet_url"] points to the same Google Sheet
    sh = gc.open_by_url(st.secrets["settings"]["sheet_url"])
    try:
        ws = sh.worksheet(sheet_tab)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=sheet_tab, rows=1000, cols=20)
        # Initialize headers
        ws.update(
            "A1:F1",
            [["Ticker", "Shares", "Avg Cost", "Currency", "Notes", "Last Updated"]]
        )
    return ws

def sheet_to_df(ws) -> pd.DataFrame:
    vals = ws.get_all_values()
    if not vals:
        return pd.DataFrame(columns=["Ticker", "Shares", "Avg Cost", "Currency", "Notes", "Last Updated"])
    df = pd.DataFrame(vals[1:], columns=vals[0])  # drop header row into columns
    # Coerce numeric columns
    for col in ["Shares", "Avg Cost"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    # Normalize blanks
    for col in ["Ticker", "Currency", "Notes"]:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()
    return df

def df_to_sheet(ws, df: pd.DataFrame):
    # Ensure required columns exist
    base_cols = ["Ticker", "Shares", "Avg Cost", "Currency", "Notes", "Last Updated"]
    for c in base_cols:
        if c not in df.columns:
            df[c] = "" if c not in ("Shares", "Avg Cost") else None

    # Trim/Order columns for persistence
    out = df[base_cols].copy()

    # Replace NaN with blanks for Sheets
    out = out.where(pd.notna(out), "")

    rows = [out.columns.tolist()] + out.values.tolist()
    # Overwrite the whole sheet range safely
    ws.clear()
    ws.update(f"A1:{chr(ord('A') + len(out.columns) - 1)}{len(rows)}", rows)

# ============================
#        QUOTE HELPERS
# ============================
@st.cache_data(ttl=45, show_spinner=False)
def fetch_quotes(tickers: List[str]) -> pd.DataFrame:
    """Batch fetch latest prices and day changes for tickers."""
    tickers = [t.strip().upper() for t in tickers if t and isinstance(t, str)]
    tickers = sorted(set(tickers))
    if not tickers:
        return pd.DataFrame(columns=["Ticker", "Price", "Day %", "Prev Close", "Time"])

    # yfinance fast batch: use Ticker().history or download
    # download is reliable for multiple tickers intraday
    try:
        hist = yf.download(tickers=tickers, period="1d", interval="1m", group_by="ticker", auto_adjust=False, progress=False)
    except Exception:
        hist = pd.DataFrame()

    quotes = []
    ts_now = pd.Timestamp.utcnow().isoformat()
    for t in tickers:
        price = None
        prev_close = None
        day_pct = None

        try:
            if isinstance(hist.columns, pd.MultiIndex):
                # Multi-ticker frame
                sub = hist[t]
            else:
                # Single ticker returns a flat frame
                sub = hist
            if not sub.empty:
                last = sub.iloc[-1]
                price = float(last["Close"])
                # Get previous close with yfinance Ticker().info or .fast_info
                fi = yf.Ticker(t).fast_info
                prev_close = float(fi.get("previous_close", float("nan")))
                # Compute day change %
                if prev_close and not math.isnan(prev_close) and prev_close != 0:
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

    qdf = pd.DataFrame(quotes)
    return qdf

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
st.title("💼 Portfolio Tracker")

colA, colB, colC = st.columns([2,1,1])
with colA:
    st.caption("Edit your holdings below. The *first five columns* are editable and persist to Google Sheets.")
with colB:
    auto_refresh = st.toggle("Auto-refresh", value=True, help="Refresh quotes every ~30s")
with colC:
    interval = st.selectbox("Refresh Interval (sec)", [15, 30, 45, 60], index=1)

if auto_refresh:
    st.autorefresh(interval=interval * 1000, key="autorefresh_portfolio")

# Load from Google Sheets
ws = get_worksheet(SHEET_TAB_NAME)
base_df = sheet_to_df(ws)

# Ensure required columns
for col in ["Ticker", "Shares", "Avg Cost", "Currency", "Notes", "Last Updated"]:
    if col not in base_df.columns:
        base_df[col] = "" if col in ("Ticker", "Currency", "Notes", "Last Updated") else None

# Empty-state starter row
if base_df.empty:
    base_df = pd.DataFrame([{"Ticker":"QQQ","Shares":10,"Avg Cost":420.00,"Currency":"USD","Notes":"Sample","Last Updated":""}])

st.subheader("Holdings (editable)")
edited = st.data_editor(
    base_df[["Ticker","Shares","Avg Cost","Currency","Notes","Last Updated"]],
    num_rows="dynamic",
    use_container_width=True,
    hide_index=True,
    column_config={
        "Ticker": st.column_config.TextColumn(help="e.g., QQQ, NVDA, AAPL"),
        "Shares": st.column_config.NumberColumn(format="%.4f", help="Can be fractional"),
        "Avg Cost": st.column_config.NumberColumn(format="%.4f"),
        "Currency": st.column_config.TextColumn(help="Optional (e.g., USD/CAD)"),
        "Notes": st.column_config.TextColumn(),
        "Last Updated": st.column_config.TextColumn(disabled=True),
    },
)

# Save controls
save_col1, save_col2, _ = st.columns([1,1,6])
with save_col1:
    do_save = st.button("💾 Save to Sheet", type="primary", use_container_width=True)
with save_col2:
    add_row = st.button("➕ Add Row", use_container_width=True)

if add_row:
    edited = pd.concat(
        [edited, pd.DataFrame([{"Ticker":"", "Shares":0.0, "Avg Cost":0.0, "Currency":"", "Notes":"", "Last Updated":""}])],
        ignore_index=True
    )

# Data cleansing: drop fully blank rows
mask_nonblank = edited["Ticker"].astype(str).str.strip() != ""
edited = edited[mask_nonblank].copy()

# Live quotes merge
tickers = edited["Ticker"].fillna("").astype(str).str.strip().tolist()
qdf = fetch_quotes(tickers)

merged = edited.merge(qdf, on="Ticker", how="left")

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
total_pl_pct = (total_pl / total_cb) * 100 if total_cb else float("nan")

# Weights
merged["Weight %"] = (merged["Market Value"] / total_mv * 100) if total_mv else 0.0

st.subheader("Live Valuation")
# Nice compact view
view_cols = [
    "Ticker","Shares","Avg Cost","Price","Market Value","Cost Basis","P/L $","P/L %","Day %","Weight %"
]
show = merged[view_cols].copy()
# Formatting
for c in ["Avg Cost","Price","Market Value","Cost Basis","P/L $"]:
    show[c] = show[c].apply(lambda x: fmt2(x))
for c in ["P/L %","Day %","Weight %"]:
    show[c] = show[c].apply(lambda x: ("" if x is None or (isinstance(x,float) and math.isnan(x)) else f"{x:.2f}%"))

st.dataframe(show, use_container_width=True, hide_index=True)

# Totals Summary
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Market Value", f"{fmt2(total_mv)}")
m2.metric("Total Cost Basis", f"{fmt2(total_cb)}")
m3.metric("Total P/L $", f"{fmt2(total_pl)}")
m4.metric("Total P/L %", ("" if math.isnan(total_pl_pct) else f"{total_pl_pct:.2f}%"))

st.caption("Prices auto-refresh based on your interval. Calculations use the latest fetched price and your saved Shares/Avg Cost.")

# Persist if requested
if do_save:
    to_save = edited.copy()
    to_save["Last Updated"] = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M:%S UTC")
    try:
        df_to_sheet(ws, to_save)
        st.success("Saved to Google Sheet ✅")
        time.sleep(0.3)
        st.rerun()
    except Exception as e:
        st.error(f"Save failed: {e}")
