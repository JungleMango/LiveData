# LiveData.py — optimized watchlist with fast batched fetch + safe Sheets I/O + 2-dec ceil rounding

import json, re, time, math
from typing import Dict, List
import pandas as pd
import yfinance as yf
import streamlit as st
import gspread
from google.oauth2 import service_account

# ============================
#            CONFIG
# ============================
st.set_page_config(
    page_title="Multi-Portfolio Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Subtle highlight for the first column (Ticker) to show it's the only editable one
st.markdown("""
<style>
[data-testid="stDataEditor"] table tr td:first-child,
[data-testid="stDataEditor"] table tr th:first-child {
  background-color: rgba(138,43,226,0.08);
}
</style>
""", unsafe_allow_html=True)

SHEET_TAB_NAME = "Watchlist"  # worksheet name inside your Google Sheet

# ============================
#         UI / UTIL
# ============================
def color_by_sign(val):
    """Return CSS to color numbers by sign."""
    if pd.isna(val):
        return ""
    try:
        v = float(val)
    except Exception:
        return ""
    if v > 0:
        return "color: #10B981; font-weight: 600;"   # green
    if v < 0:
        return "color: #EF4444; font-weight: 600;"   # red
    return "color: #6B7280;"                         # gray for zero


def colored_header_bg(
    title: str,
    bg_color: str = "#8A2BE2",
    text_color: str = "white",
    font_size: int = 26,
    align: str = "center",
    gradient: bool = True
):
    """
    Create a clean, centered header with optional gradient background.
    
    Parameters:
        title (str): The header text (supports emojis).
        bg_color (str): Base color (e.g., "#8A2BE2").
        text_color (str): Font color (default "white").
        font_size (int): Font size in px (default 26).
        align (str): "center", "left", or "right".
        gradient (bool): Whether to apply a gradient effect.
    """
    gradient_css = (
        f"linear-gradient(135deg, {bg_color} 0%, {bg_color}AA 100%)"
        if gradient else bg_color
    )

    st.markdown(
        f"""
        <div style="
            background: {gradient_css};
            color: {text_color};
            padding: 14px;
            border-radius: 12px;
            font-size: {font_size}px;
            font-weight: 700;
            text-align: {align};
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            margin-top: 10px;
            margin-bottom: 20px;
            letter-spacing: 0.5px;">
            {title}
        </div>
        """,
        unsafe_allow_html=True,
    )

def normalize_watch_df(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({"Ticker": df.get("Ticker", pd.Series([], dtype=str))})
    out["Ticker"] = out["Ticker"].astype(str).str.upper().str.strip()
    out = out[out["Ticker"] != ""]
    return out[["Ticker"]]

def signature(df: pd.DataFrame) -> int:
    tickers = df["Ticker"].tolist() if "Ticker" in df.columns else []
    return hash(tuple(tickers))

def _tickers_norm(tickers: List[str]) -> List[str]:
    return [t for t in pd.unique(pd.Series(tickers).astype(str).str.upper().str.strip()) if t]

def round2_up(value):
    """Round up to 2 decimal places (ceil style)."""
    try:
        if pd.isna(value):
            return None
        return math.ceil(float(value) * 100) / 100.0
    except Exception:
        return None
    

# ============================
#     GOOGLE SHEETS HELPERS
# ============================
def _assert_sheets_secrets():
    if "sheets" not in st.secrets:
        st.error("Missing [sheets] in secrets (App → Settings → Secrets, or .streamlit/secrets.toml).")
        st.stop()
    s = st.secrets["sheets"]
    for k in ("sheet_id", "service_account"):
        if k not in s:
            st.error(f"Missing key in [sheets]: {k}")
            st.stop()

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

def _open_or_create_worksheet(client: gspread.Client, sheet_id: str, tab_name: str):
    sh = client.open_by_key(sheet_id)
    try:
        ws = sh.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=tab_name, rows=1000, cols=5)
        ws.update("A1", [["Ticker"]])
    return ws

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

def save_watchlist_to_sheet(df: pd.DataFrame, prevent_empty: bool = True) -> bool:
    """
    Safely write tickers to column A.
    - Skips saving if df is empty (to avoid hard reset).
    - Clears only A2:A (keeps header/other columns intact).
    Returns True if saved, False if skipped.
    """
    clean = normalize_watch_df(df)
    if prevent_empty and clean.empty:
        st.warning("Skipped save: watchlist is empty (won’t overwrite the sheet).")
        return False

    client = get_sheet_client()
    ws = _open_or_create_worksheet(client, st.secrets["sheets"]["sheet_id"], SHEET_TAB_NAME)

    data = [["Ticker"]] + [[t] for t in clean["Ticker"].tolist()]

    try:
        ws.batch_clear(["A2:A"])  # clear only data rows, not header
    except Exception:
        pass

    ws.update("A1", data)
    return True

def sheets_configured() -> bool:
    try:
        s = st.secrets["sheets"]
        return bool(s.get("sheet_id")) and bool(s.get("service_account"))
    except Exception:
        return False

# ============================
#        MARKET HELPERS
# ============================
@st.cache_data(ttl=60)
def fetch_watch_batched(tickers: List[str], days: int = 60, _key: str = ""):
    """
    Single batched call for:
      - last price map
      - prev close map
      - history (Series per ticker, last 'days')
    _key is a cache-buster (e.g., '|'.join(sorted(tickers)) + f':{days}').
    """
    tks = _tickers_norm(tickers)
    result = {
        "last_price": {t: None for t in tks},
        "prev_close": {t: None for t in tks},
        "history":    {t: pd.Series(dtype=float) for t in tks},
    }
    if not tks:
        return result

    period = f"{max(days, 7)}d"
    try:
        df = yf.download(
            tickers=tks, period=period, interval="1d",
            group_by="ticker", progress=False, threads=True, auto_adjust=False
        )
    except Exception:
        return result

    def _fill(frame: pd.DataFrame, t: str):
        if frame is None or frame.empty: return
        s = frame["Close"].dropna()
        if s.empty: return
        s = s.tail(days)  # trim early
        result["history"][t] = s
        result["last_price"][t] = float(s.iloc[-1])
        if len(s) >= 2:
            result["prev_close"][t] = float(s.iloc[-2])

    if isinstance(df.columns, pd.MultiIndex):
        for t in tks:
            try: _fill(df[t], t)
            except Exception: pass
    else:
        _fill(df, tks[0])

    return result

@st.cache_data(ttl=24*60*60)  # 1 day
def fetch_names_fast(tickers: List[str]) -> Dict[str, str]:
    names = {}
    for t in _tickers_norm(tickers):
        name = ""
        try:
            info = yf.Ticker(t).get_info()
            name = info.get("shortName") or info.get("longName") or info.get("name") or ""
        except Exception:
            pass
        names[t] = name
    return names

# ============================
#     SESSION BOOTSTRAP
# ============================
if "watchlist" not in st.session_state:
    try:
        if sheets_configured():
            df0 = get_sheet_snapshot()
        else:
            df0 = pd.DataFrame({"Ticker": ["QQQ", "AAPL", "MSFT"]})
        if df0 is None or df0.empty:
            df0 = pd.DataFrame({"Ticker": ["QQQ", "AAPL", "MSFT"]})
        st.session_state["watchlist"] = normalize_watch_df(df0)
    except Exception:
        st.session_state["watchlist"] = pd.DataFrame({"Ticker": ["QQQ", "AAPL", "MSFT"]})

# Initialize "last saved" signature from the sheet
if "watchlist_saved_sig" not in st.session_state:
    try:
        current_on_sheet = get_sheet_snapshot()
        st.session_state["watchlist_saved_sig"] = signature(current_on_sheet)
    except Exception:
        st.session_state["watchlist_saved_sig"] = signature(st.session_state["watchlist"])

# Debounce timer for autosave (optional)
if "_wl_last_edit_ts" not in st.session_state:
    st.session_state["_wl_last_edit_ts"] = 0.0

# ============================
#           WATCHLIST UI
# ============================
colored_header_bg("👀 Watchlist", "#8A2BE2", "white", 26)

# Build base + normalize
curr = normalize_watch_df(st.session_state["watchlist"])
tickers = curr["Ticker"].unique().tolist()

# --- Batched data fetch (fast path) ---
cache_key = "|".join(sorted(tickers)) + ":60d"
bundle = fetch_watch_batched(tickers, days=60, _key=cache_key)
last_price = bundle["last_price"]
prev_close = bundle["prev_close"]
history    = bundle["history"]

# Derived metrics (local, rounded up to 2dp)
def _pct_7d(s: pd.Series):
    if s is None or s.empty or len(s) < 8: return None
    return round2_up((float(s.iloc[-1]) / float(s.iloc[-8]) - 1) * 100)

def _last_30(s: pd.Series):
    return [] if s is None or s.empty else [round2_up(x) for x in s.tail(30).tolist()]

changes_rows = []
for t in tickers:
    p0, p1 = prev_close.get(t), last_price.get(t)
    chg = round2_up((p1/p0 - 1)*100) if (p0 and p1) else None
    changes_rows.append({"Ticker": t, "Daily Change %": chg})
changes_df = pd.DataFrame(changes_rows)

map_7d  = {t: _pct_7d(history.get(t)) for t in tickers}
map_30 = {t: _last_30(history.get(t)) for t in tickers}

# Names (slow path, but cached 1 day)
name_map = fetch_names_fast(tickers)

# --- Compose table view ---
view = curr.copy()
view["Name"] = view["Ticker"].map(name_map)
view["Live Price"] = view["Ticker"].map(last_price).apply(round2_up)
view = view.merge(changes_df, on="Ticker", how="left")
view["7D % Change"] = view["Ticker"].map(map_7d)
view["30D Trend"] = view["Ticker"].map(map_30)

# Safe sparkline setup
LineChartColumn = getattr(st.column_config, "LineChartColumn", None)
chart_col = LineChartColumn() if LineChartColumn is not None else st.column_config.ListColumn(
    help="Upgrade Streamlit to enable inline charts."
)

# --- Editable table (Ticker editable only) ---
edited = st.data_editor(
    view,
    width="stretch",
    key="watchlist_editor_single",
    num_rows="dynamic",
    column_config={
        "Ticker": st.column_config.TextColumn(
            help="Yahoo Finance symbol, e.g., MSFT, ETH-USD, XAUUSD=X"
        ),
        "Name": st.column_config.TextColumn(help="Company / Asset name", disabled=True),
        "Live Price": st.column_config.NumberColumn(format="$%.2f"),
        "Daily Change %": st.column_config.NumberColumn(format="%.2f%%"),
        "7D % Change": st.column_config.NumberColumn(format="%.2f%%"),
        "30D Trend": chart_col,
    },
    disabled=["Name", "Live Price", "Daily Change %", "7D % Change", "30D Trend"],
)

st.markdown("#### 📋 Styled View")
styled = (
    view
    .copy()
    .style
    .format({
        "Live Price": "${:,.2f}",
        "Daily Change %": "{:,.2f}%",
        "7D % Change": "{:,.2f}%",
    })
    .applymap(color_by_sign, subset=["Daily Change %", "7D % Change"])
)

st.dataframe(styled, use_container_width=True)


# Persist in-memory
st.session_state["watchlist"] = normalize_watch_df(edited[["Ticker"]])
st.session_state["_wl_last_edit_ts"] = time.time()

# 1) Base tickers from session (or empty)
base = st.session_state.get("watchlist", pd.DataFrame({"Ticker": []}))
curr = normalize_watch_df(base) if "normalize_watch_df" in globals() else base
tickers = curr["Ticker"].unique().tolist()

# 2) Fetch batched market data (uses your existing helper)
#    Cache key so reruns are instant unless tickers change
cache_key = "|".join(sorted(tickers)) + ":60d"
bundle = fetch_watch_batched(tickers, days=60, _key=cache_key) if tickers else {"last_price":{}, "prev_close":{}, "history":{}}
last_price = bundle.get("last_price", {})
prev_close = bundle.get("prev_close", {})
history    = bundle.get("history", {})

# 3) Local helpers (no network)
def round2_up(x):
    import math, pandas as _pd
    try:
        return None if _pd.isna(x) else math.ceil(float(x)*100)/100.0
    except Exception:
        return None

def _pct_7d(s: pd.Series):
    if s is None or s.empty or len(s) < 8: return None
    return round2_up((float(s.iloc[-1]) / float(s.iloc[-8]) - 1) * 100)

def _last_30(s: pd.Series):
    return [] if s is None or s.empty else [round2_up(x) for x in s.tail(30).tolist()]

# daily % change from prev_close -> last
rows = []
for t in tickers:
    p0, p1 = prev_close.get(t), last_price.get(t)
    chg = round2_up((p1/p0 - 1)*100) if (p0 and p1) else None
    rows.append({"Ticker": t, "Daily Change %": chg})
changes_df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["Ticker","Daily Change %"])

map_7d  = {t: _pct_7d(history.get(t)) for t in tickers}
map_30 = {t: _last_30(history.get(t)) for t in tickers}

# 4) Optional: names (cached helper you already have)
name_map = fetch_names_fast(tickers) if tickers else {}

# 5) Compose the 'view' DataFrame
view = curr.copy()
view["Name"] = view["Ticker"].map(name_map)
view["Live Price"] = view["Ticker"].map(last_price).apply(round2_up)
view = view.merge(changes_df, on="Ticker", how="left")
view["7D % Change"] = view["Ticker"].map(map_7d)
view["30D Trend"]   = view["Ticker"].map(map_30)

# 6) Arrow columns (safe even if columns are missing)
def with_arrow(x):
    if pd.isna(x): return ""
    try: x = float(x)
    except Exception: return ""
    arrow = "▲" if x > 0 else ("▼" if x < 0 else "")
    color = "#10B981" if x > 0 else ("#EF4444" if x < 0 else "#6B7280")
    return f'<span style="color:{color};font-weight:600;">{arrow} {abs(x):.2f}%</span>'

view["Daily Δ"] = view["Daily Change %"].apply(with_arrow) if "Daily Change %" in view.columns else ""
view["7D Δ"]    = view["7D % Change"].apply(with_arrow)    if "7D % Change" in view.columns else ""

# ============================
#      SAVE / RELOAD / REFRESH
# ============================
c1, c2, c3 = st.columns([1,1,1])
with c1:
    if st.button("💾 Save Now"):
        if st.session_state["watchlist"].empty:
            st.warning("Won’t overwrite with an empty list. Add at least one ticker.")
        elif save_watchlist_to_sheet(st.session_state["watchlist"], prevent_empty=True):
            st.success("Saved to Google Sheets.")
            st.session_state["watchlist_saved_sig"] = signature(st.session_state["watchlist"])

with c2:
    if st.button("↩️ Reload from Sheet"):
        st.session_state["watchlist"] = get_sheet_snapshot()
        st.session_state["watchlist_saved_sig"] = signature(st.session_state["watchlist"])
        st.rerun()

with c3:
    if st.button("🔄 Refresh Data (clear cache)"):
        st.cache_data.clear()
        st.rerun()

# ============================
#          AUTOSAVE SAFE
# ============================
current_sig = signature(st.session_state["watchlist"])
last_saved_sig = st.session_state.get("watchlist_saved_sig")
if (
    sheets_configured()
    and last_saved_sig is not None
    and current_sig != last_saved_sig
    and not st.session_state["watchlist"].empty
    and time.time() - st.session_state["_wl_last_edit_ts"] > 1.5
):
    if save_watchlist_to_sheet(st.session_state["watchlist"], prevent_empty=True):
        st.toast("Autosaved to Google Sheets")
        st.session_state["watchlist_saved_sig"] = current_sig
