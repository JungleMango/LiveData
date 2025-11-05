# LiveData.py
import json
from pathlib import Path
from typing import Dict, List

import pandas as pd
import yfinance as yf
import altair as alt
import streamlit as st
from urllib.parse import quote, unquote
import gspread
from google.oauth2 import service_account

with st.expander("🛠 Sheets secrets check"):
    try:
        raw = st.secrets["sheets"]["service_account"]
        st.write("Type of service_account in secrets:", type(raw).__name__)
        if isinstance(raw, str):
            st.write("Starts with:", raw.strip()[:20])
    except Exception as e:
        st.exception(e)


# ---------- Page config ----------
st.set_page_config(
    page_title="Multi-Portfolio Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- UI helpers ----------
@st.cache_resource
def _assert_sheets_secrets():
    if "sheets" not in st.secrets:
        st.error("Missing [sheets] in secrets. Add it in App → Settings → Secrets or .streamlit/secrets.toml.")
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

    # Accept either a dict (already parsed) or a JSON string
    if isinstance(raw, dict):
        info = raw
    else:
        try:
            info = json.loads(raw)
        except Exception as e:
            # Helpful hint if the private_key likely has raw newlines
            st.error(
                "Couldn't parse service_account JSON from secrets. "
                "Most likely the `private_key` needs `\\n` (double backslash) line breaks.\n\n"
                "Fix in secrets: replace every \\n in private_key with \\\\n."
            )
            st.exception(e)
            st.stop()

    creds = service_account.Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return gspread.authorize(creds)

def save_watchlist_to_sheet(df: pd.DataFrame):
    client = get_sheet_client()
    sheet = client.open_by_key(st.secrets["sheets"]["sheet_id"]).sheet1
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.values.tolist())
    st.success("✅ Watchlist saved to Google Sheets!")

def load_watchlist_from_sheet() -> pd.DataFrame:
    client = get_sheet_client()
    sheet = client.open_by_key(st.secrets["sheets"]["sheet_id"]).sheet1
    data = sheet.get_all_records()
    return pd.DataFrame(data)

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
        unsafe_allow_html=True
    )

# ---------- State bootstrap ----------
# ---- 1) Bootstrap (unchanged) ----
if "watchlist" not in st.session_state or st.session_state["watchlist"] is None:
    st.session_state["watchlist"] = pd.DataFrame({"Ticker": ["QQQ", "AAPL", "MSFT"]})

# ---- 2) Editor (make sure this comes before autosave) ----




# ---------- Price utilities ----------
@st.cache_data(ttl=45)
def fetch_latest_prices(tickers: List[str]) -> Dict[str, float]:
    """
    Return a mapping {ticker: last_close or None} for the given tickers.
    Uses a batched yfinance download for speed, with a per-ticker fallback.
    """
    tickers = [t for t in pd.unique(pd.Series(tickers).astype(str).str.upper().str.strip()) if t]
    out: Dict[str, float] = {t: None for t in tickers}
    if not tickers:
        return out

    try:
        df = yf.download(
            tickers=tickers,
            period="5d",        # use a few days so we can still compute change and handle holidays
            interval="1d",
            group_by="ticker",
            progress=False,
            threads=True,
        )
        if isinstance(df.columns, pd.MultiIndex):
            # Multi-ticker frame
            for t in tickers:
                try:
                    d = df[t].dropna()
                    if not d.empty:
                        out[t] = float(d["Close"].iloc[-1])
                except Exception:
                    pass
        else:
            # Single-ticker frame
            d = df.dropna()
            if not d.empty:
                out[tickers[0]] = float(d["Close"].iloc[-1])
    except Exception:
        # Fall back silently; we'll try per-ticker below if needed
        pass

    # Per-ticker fallback for any missing values
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
def day_change(tickers: List[str]) -> pd.DataFrame:
    """
    Compute previous-close to last-close daily % change for each ticker.
    Returns DataFrame with columns ["Ticker", "Daily Change %"].
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
        )
        if isinstance(df.columns, pd.MultiIndex):
            for t in tickers:
                try:
                    d = df[t].dropna()
                    if len(d) >= 2:
                        prev_close = float(d["Close"].iloc[-2])
                        last_close = float(d["Close"].iloc[-1])
                        change = round((last_close / prev_close - 1) * 100, 2)
                        rows.append({"Ticker": t, "Daily Change %": change})
                except Exception:
                    pass
        else:
            d = df.dropna()
            if len(d) >= 2:
                prev_close = float(d["Close"].iloc[-2])
                last_close = float(d["Close"].iloc[-1])
                change = round((last_close / prev_close - 1) * 100, 2)
                rows.append({"Ticker": tickers[0], "Daily Change %": change})
    except Exception:
        pass
    return pd.DataFrame(rows, columns=["Ticker", "Daily Change %"])

# ============================
#        WATCHLIST UI
# ============================
colored_header_bg("👀 Watchlist", "#8A2BE2", "white", 26)

watch_edited = st.data_editor(
    st.session_state["watchlist"],
    num_rows="dynamic",
    use_container_width=True,
    key="watchlist_editor",
    column_config={
        "Ticker": st.column_config.TextColumn(
            help="Any Yahoo Finance symbol, e.g., MSFT, ETH-USD, XAUUSD=X"
        ),
    },
)
st.session_state["watchlist"] = watch_edited

# Build working DataFrame
watch = st.session_state["watchlist"].copy()
if "Ticker" not in watch.columns:
    watch["Ticker"] = ""
watch["Ticker"] = watch["Ticker"].astype(str).str.upper().str.strip()

# Unique, non-empty tickers
tickers = [t for t in watch["Ticker"].unique().tolist() if t]

# Fetch latest prices (cached)
prices_map = fetch_latest_prices(tickers)
watch["Live Price"] = watch["Ticker"].map(prices_map)

# Fetch daily % change (cached) and merge
wl_changes = day_change(tickers)
watch = watch.merge(wl_changes, on="Ticker", how="left")

# Display
st.dataframe(
    watch.style.format({"Live Price": "${:,.4f}", "Daily Change %": "{:,.2f}%"}),
    use_container_width=True,
)

# ---- 3) Autosave (after editor) ----
def _normalize_watch_df(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({"Ticker": df.get("Ticker", pd.Series([], dtype=str))})
    out["Ticker"] = out["Ticker"].astype(str).str.upper().str.strip()
    out = out.dropna(subset=["Ticker"])
    return out[["Ticker"]]

def _signature(df: pd.DataFrame) -> int:
    # Stable signature: tuple of cleaned tickers in order + length
    tickers = df["Ticker"].tolist() if "Ticker" in df.columns else []
    return hash((tuple(tickers), len(tickers)))

curr = _normalize_watch_df(st.session_state["watchlist"])
sig = _signature(curr)

prev_sig = st.session_state.get("_watchlist_sig")

# Only save if:
#  - we have previous signature (i.e., not the very first run), and
#  - the signature changed (i.e., user edited)
should_save = prev_sig is not None and sig != prev_sig

# Update signature every run
st.session_state["_watchlist_sig"] = sig

# Optional: guard if Sheets secrets not configured yet
sheets_ready = ("sheets" in st.secrets) and ("service_account" in st.secrets["sheets"]) and ("sheet_id" in st.secrets["sheets"])

if should_save and sheets_ready:
    try:
        save_watchlist_to_sheet(curr)
        st.toast("Autosaved to Sheets")
    except Exception as e:
        st.warning(f"Autosave failed: {e}")



c1, c2 = st.columns([1, 1])
with c1:
    if st.button("💾 Save to Sheets"):
        save_watchlist_to_sheet(st.session_state["watchlist"])
with c2:
    if st.button("⬆️ Load from Sheets"):
        st.session_state["watchlist"] = load_watchlist_from_sheet()
        st.success("Loaded watchlist from Google Sheets!")


# Optional: little note about data freshness
st.caption("Prices and daily change cached for ~45–60 seconds to keep things snappy.")
