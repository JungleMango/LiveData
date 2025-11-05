# LiveData.py
import json
import re
from typing import Dict, List

import pandas as pd
import yfinance as yf
import streamlit as st
import gspread
from google.oauth2 import service_account

# ============================
#          CONFIG
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
/* Target the first column cells & header inside data editor */
[data-testid="stDataEditor"] table tr td:first-child,
[data-testid="stDataEditor"] table tr th:first-child {
  background-color: rgba(138,43,226,0.08); /* light purple tint */
}
</style>
""", unsafe_allow_html=True)


SHEET_TAB_NAME = "Watchlist"  # worksheet name inside your Google Sheet

# ============================
#       UI / UTIL HELPERS
# ============================
def colored_header_bg(title: str, bg_color: str, text_color: str = "white", font_size: int = 26):
    st.markdown(
        f"""
        <div style="
            background-color: {bg_color};
            color: {text_color};
            padding: 10px;
            border-radius: 8px;
            font-size: {font_size}px;
            font-weight: bold;
            text-align: left;">
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

def save_watchlist_to_sheet(df: pd.DataFrame):
    client = get_sheet_client()
    ws = _open_or_create_worksheet(client, st.secrets["sheets"]["sheet_id"], SHEET_TAB_NAME)
    clean = normalize_watch_df(df)
    ws.clear()
    values = [clean.columns.tolist()] + clean.values.tolist() if not clean.empty else [["Ticker"]]
    ws.update("A1", values)
    st.success(f"✅ Saved {0 if clean.empty else len(clean)} tickers to Google Sheets ({SHEET_TAB_NAME}).")

def load_watchlist_from_sheet() -> pd.DataFrame:
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
def fetch_latest_prices_batched(tickers: List[str]) -> Dict[str, float]:
    """
    Return {ticker: last_close or None}. Batches with yf.download for speed,
    then falls back to per-ticker if needed.
    """
    tickers = [t for t in pd.unique(pd.Series(tickers).astype(str).str.upper().str.strip()) if t]
    out: Dict[str, float] = {t: None for t in tickers}
    if not tickers:
        return out

    try:
        df = yf.download(
            tickers=tickers,
            period="5d",
            interval="1d",
            group_by="ticker",
            progress=False,
            threads=True,
            auto_adjust=False,  # be explicit
        )
        if isinstance(df.columns, pd.MultiIndex):
            for t in tickers:
                try:
                    d = df[t].dropna()
                    if not d.empty:
                        out[t] = float(d["Close"].iloc[-1])
                except Exception:
                    pass
        else:
            d = df.dropna()
            if not d.empty:
                out[tickers[0]] = float(d["Close"].iloc[-1])
    except Exception:
        pass

    # Per-ticker fallback
    missing = [t for t, v in out.items() if v is None]
    for t in missing:
        try:
            h = yf.Ticker(t).history(period="5d", interval="1d")
            if not h.empty:
                out[t] = float(h["Close"].iloc[-1])
        except Exception:
            out[t] = None
    return out

@st.cache_data(ttl=60)
def day_change_pct(tickers: List[str]) -> pd.DataFrame:
    """
    Compute previous-close → last-close daily % change.
    Returns DataFrame ["Ticker","Daily Change %"].
    """
    tickers = [t for t in pd.unique(pd.Series(tickers).astype(str).str.upper().str.strip()) if t]
    if not tickers:
        return pd.DataFrame(columns=["Ticker", "Daily Change %"])

    rows = []
    try:
        df = yf.download(
            tickers=tickers,
            period="5d",
            interval="1d",
            group_by="ticker",
            progress=False,
            threads=True,
            auto_adjust=False,
        )
        if isinstance(df.columns, pd.MultiIndex):
            for t in tickers:
                try:
                    d = df[t].dropna()
                    if len(d) >= 2:
                        prev_close = float(d["Close"].iloc[-2])
                        last_close = float(d["Close"].iloc[-1])
                        rows.append({"Ticker": t, "Daily Change %": round((last_close / prev_close - 1) * 100, 2)})
                except Exception:
                    pass
        else:
            d = df.dropna()
            if len(d) >= 2:
                prev_close = float(d["Close"].iloc[-2])
                last_close = float(d["Close"].iloc[-1])
                rows.append({"Ticker": tickers[0], "Daily Change %": round((last_close / prev_close - 1) * 100, 2)})
    except Exception:
        pass
    return pd.DataFrame(rows, columns=["Ticker", "Daily Change %"])

@st.cache_data(ttl=300)
def recent_history(tickers: List[str], days: int = 60) -> Dict[str, pd.Series]:
    """
    Returns {ticker: Series of daily Close (last <=days)} using one batched download.
    """
    out: Dict[str, pd.Series] = {t: pd.Series(dtype=float) for t in tickers}
    if not tickers:
        return out

    df = yf.download(
        tickers=tickers,
        period=f"{days}d",
        interval="1d",
        group_by="ticker",
        progress=False,
        threads=True,
        auto_adjust=False,
    )

    if isinstance(df.columns, pd.MultiIndex):
        for t in tickers:
            try:
                d = df[t]["Close"].dropna()
                out[t] = d
            except Exception:
                pass
    else:
        # single ticker case
        try:
            d = df["Close"].dropna()
            out[tickers[0]] = d
        except Exception:
            pass
    return out

@st.cache_data(ttl=24 * 60 * 60)  # 1 day cache
def fetch_names(tickers: List[str]) -> Dict[str, str]:
    out = {}
    for t in tickers:
        name = None
        try:
            info = yf.Ticker(t).get_info()  # ok for small lists; cached
            name = info.get("shortName") or info.get("longName")
        except Exception:
            pass
        out[t] = name or ""
    return out



# ============================
#     SESSION BOOTSTRAP
# ============================
if "watchlist" not in st.session_state:
    try:
        if sheets_configured():
            df0 = load_watchlist_from_sheet()
        else:
            df0 = pd.DataFrame({"Ticker": ["QQQ", "AAPL", "MSFT"]})
        if df0 is None or df0.empty:
            df0 = pd.DataFrame({"Ticker": ["QQQ", "AAPL", "MSFT"]})
        st.session_state["watchlist"] = normalize_watch_df(df0)
        st.session_state["_watchlist_sig"] = None
    except Exception:
        st.session_state["watchlist"] = pd.DataFrame({"Ticker": ["QQQ", "AAPL", "MSFT"]})
        st.session_state["_watchlist_sig"] = None

# ============================
#         WATCHLIST UI
# ============================
colored_header_bg("👀 Watchlist", "#8A2BE2", "white", 26)

# Build computed columns
curr = normalize_watch_df(st.session_state["watchlist"])
tickers = [t for t in curr["Ticker"].unique().tolist() if t]

names_map   = fetch_names(tickers)
prices_map  = fetch_latest_prices_batched(tickers)
changes_df  = day_change_pct(tickers)   # ["Ticker","Daily Change %"]
hist_map    = recent_history(tickers, days=60)

def _pct_7d(series: pd.Series):
    if series is None or series.empty or len(series) < 8:
        return None
    last = float(series.iloc[-1])
    prev = float(series.iloc[-8])  # ~7 trading sessions ago
    if prev == 0:
        return None
    return round((last / prev - 1) * 100, 2)

def _last_30(series: pd.Series):
    if series is None or series.empty:
        return []
    return [float(x) for x in series.tail(30).tolist()]

map_7d = {t: _pct_7d(hist_map.get(t)) for t in tickers}
map_30 = {t: _last_30(hist_map.get(t)) for t in tickers}

# Compose the view (Ticker editable; others computed)
view = curr.copy()
view["Name"]          = view["Ticker"].map(names_map)
view["Live Price"]    = view["Ticker"].map(prices_map)
view                   = view.merge(changes_df, on="Ticker", how="left")
view["7D % Change"]   = view["Ticker"].map(map_7d)
view["30D Trend"]     = view["Ticker"].map(map_30)

# Version-safe chart column
LineChartColumn = getattr(st.column_config, "LineChartColumn", None)
chart_col = LineChartColumn() if LineChartColumn else st.column_config.ListColumn(
    help="Upgrade Streamlit to enable in-cell line charts for this column."
)

# Single editable table: only 'Ticker' is editable
edited = st.data_editor(
    view,
    width="stretch",
    key="watchlist_editor_single",
    num_rows="dynamic",
    column_order=["Ticker", "Name", "Live Price", "Daily Change %", "7D % Change", "30D Trend"],
    column_config={
        "Ticker": st.column_config.TextColumn(
            help="Enter any Yahoo Finance symbol, e.g., MSFT, ETH-USD, XAUUSD=X",
            required=True,
            max_chars=32,
            placeholder="e.g., AAPL",
        ),
        "Name": st.column_config.TextColumn(help="Company / asset name (auto)", disabled=True),
        "Live Price": st.column_config.NumberColumn(format="$%.4f"),
        "Daily Change %": st.column_config.NumberColumn(format="%.2f%%"),
        "7D % Change": st.column_config.NumberColumn(format="%.2f%%"),
        "30D Trend": chart_col,
    },
    # lock everything except Ticker
    disabled=["Name", "Live Price", "Daily Change %", "7D % Change", "30D Trend"],
)

# Persist only Ticker back to state (the rest are computed)
st.session_state["watchlist"] = normalize_watch_df(edited[["Ticker"]])

# Autosave after edits (if Sheets configured)
sig  = signature(st.session_state["watchlist"])
prev = st.session_state.get("_watchlist_sig")
if sheets_configured() and prev is not None and sig != prev:
    try:
        save_watchlist_to_sheet(st.session_state["watchlist"])
        st.toast("Autosaved to Google Sheets")
    except Exception as e:
        st.warning(f"Autosave failed: {e}")
st.session_state["_watchlist_sig"] = sig
