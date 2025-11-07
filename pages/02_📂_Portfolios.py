pages/02_📂_Portfolios.py
+227
-20

import json
import re
from pathlib import Path
from typing import Dict, List

import pandas as pd
import yfinance as yf
import altair as alt
import streamlit as st
from urllib.parse import quote, unquote

import gspread
from google.oauth2 import service_account

st.set_page_config(
    page_title="Multi-Portfolio Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

APP_DIR   = Path(__file__).parent               # absolute dir of this script
DATA_DIR  = APP_DIR                              # or APP_DIR / "data"
DATA_FILE = DATA_DIR / "portfolios.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)      # ensure folder exists

SHEET_TAB_PORTFOLIOS = "Portfolios"
SHEET_TAB_WATCHLIST = "Watchlist"
PORTFOLIO_HEADERS = ["Portfolio", "Ticker", "Shares", "Avg Cost"]

# ⬇️ Temporary “safe boot” so you always see *something* even if later code errors
st.caption("✅ App booted — rendering helpers… (remove this once stable)")

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
@@ -203,115 +211,311 @@ def build_portfolio_history(holdings_df: pd.DataFrame, period="6mo", interval="1
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


# ---------- Google Sheets helpers ----------
def _assert_sheets_secrets():
    if "sheets" not in st.secrets:
        st.error("Missing [sheets] secrets (App → Settings → Secrets).")
        st.stop()
    s = st.secrets["sheets"]
    for key in ("sheet_id", "service_account"):
        if key not in s:
            st.error(f"Missing key in [sheets]: {key}")
            st.stop()


@st.cache_resource
def get_sheet_client():
    _assert_sheets_secrets()
    raw = st.secrets["sheets"]["service_account"]
    if isinstance(raw, dict):
        info = raw
    else:
        def _escape_private_key_newlines(payload: str) -> str:
            return re.sub(
                r'(\"private_key\"\s*:\s*\")(.*?)(\")',
                lambda m: m.group(1) + m.group(2).replace("\n", "\\n") + m.group(3),
                payload,
                flags=re.S,
            )

        info = json.loads(_escape_private_key_newlines(raw))

    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return gspread.authorize(creds)


def sheets_configured() -> bool:
    try:
        s = st.secrets["sheets"]
        return bool(s.get("sheet_id")) and bool(s.get("service_account"))
    except Exception:
        return False


def _open_or_create_worksheet(client: gspread.Client, tab_name: str, headers: List[str]):
    sheet = client.open_by_key(st.secrets["sheets"]["sheet_id"])
    try:
        ws = sheet.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sheet.add_worksheet(title=tab_name, rows=1000, cols=max(len(headers), 4))
        ws.update("A1", [headers])
        return ws

    try:
        current = ws.row_values(1)
    except Exception:
        current = []
    if [c.strip() for c in current[: len(headers)]] != headers:
        ws.update("A1", [headers])
    return ws


def load_portfolios_from_sheet() -> Dict[str, pd.DataFrame]:
    if not sheets_configured():
        return {}
    try:
        client = get_sheet_client()
        ws = _open_or_create_worksheet(client, SHEET_TAB_PORTFOLIOS, PORTFOLIO_HEADERS)
        values = ws.get_all_values()
        if not values or len(values) <= 1:
            return {}
        header, *rows = values
        df = pd.DataFrame(rows, columns=header)
        if "Portfolio" not in df.columns:
            return {}
        portfolios: Dict[str, pd.DataFrame] = {}
        df = df.replace("", pd.NA)
        for name, group in df.groupby("Portfolio"):
            if pd.isna(name):
                continue
            clean = _normalize_holdings(group[["Ticker", "Shares", "Avg Cost"]])
            clean = clean[clean["Ticker"].astype(str).str.strip() != ""]
            portfolios[name] = clean if not clean.empty else pd.DataFrame(columns=["Ticker", "Shares", "Avg Cost"])
        return portfolios
    except Exception:
        return {}


def save_portfolios_to_sheet(portfolios: Dict[str, pd.DataFrame]) -> bool:
    if not sheets_configured():
        return False
    client = get_sheet_client()
    ws = _open_or_create_worksheet(client, SHEET_TAB_PORTFOLIOS, PORTFOLIO_HEADERS)
    rows = []
    for name, df in portfolios.items():
        clean = _normalize_holdings(df)
        if clean.empty:
            rows.append([name, "", "", ""])
            continue
        for _, row in clean.iterrows():
            shares = "" if pd.isna(row["Shares"]) else float(row["Shares"])
            avg = "" if pd.isna(row["Avg Cost"]) else float(row["Avg Cost"])
            rows.append([name, row["Ticker"], shares, avg])
    data = [PORTFOLIO_HEADERS] + rows if rows else [PORTFOLIO_HEADERS]
    try:
        ws.batch_clear(["A2:D"])
    except Exception:
        pass
    ws.update("A1", data)
    return True


def load_watchlist_from_sheet() -> pd.DataFrame | None:
    if not sheets_configured():
        return None
    try:
        client = get_sheet_client()
        ws = _open_or_create_worksheet(client, SHEET_TAB_WATCHLIST, ["Ticker"])
        values = ws.get_all_values()
        if not values or len(values) <= 1:
            return pd.DataFrame(columns=["Ticker"])
        header, *rows = values
        if "Ticker" not in header:
            return None
        df = pd.DataFrame(rows, columns=header)
        df = df[["Ticker"]]
        df["Ticker"] = df["Ticker"].astype(str).str.upper().str.strip()
        df = df[df["Ticker"] != ""]
        return df
    except Exception:
        return None


def save_watchlist_to_sheet(df: pd.DataFrame) -> bool:
    if not sheets_configured():
        return False
    client = get_sheet_client()
    ws = _open_or_create_worksheet(client, SHEET_TAB_WATCHLIST, ["Ticker"])
    clean = pd.DataFrame({"Ticker": df.get("Ticker", pd.Series(dtype=str))})
    clean["Ticker"] = clean["Ticker"].astype(str).str.upper().str.strip()
    clean = clean[clean["Ticker"] != ""]
    data = [["Ticker"]] + [[t] for t in clean["Ticker"].tolist()]
    try:
        ws.batch_clear(["A2:A"])
    except Exception:
        pass
    ws.update("A1", data)
    return True


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
    portfolios: Dict[str, pd.DataFrame] = {}
    watch = None

    sheet_portfolios = load_portfolios_from_sheet()
    if sheet_portfolios:
        portfolios = sheet_portfolios

    sheet_watch = load_watchlist_from_sheet()
    if sheet_watch is not None and not sheet_watch.empty:
        watch = sheet_watch

    if not portfolios and DATA_FILE.exists():
        try:
            blob = json.loads(DATA_FILE.read_text())
            for name, rows in blob.get("portfolios", {}).items():
                portfolios[name] = _normalize_holdings(pd.DataFrame(rows))
            if watch is None:
                raw_watch = pd.DataFrame(blob.get("watchlist", []))
                if not raw_watch.empty:
                    watch = raw_watch
        except Exception:
            pass

    if not portfolios:
        portfolios = {k: v.copy() for k, v in DEFAULT.items()}
    else:
        portfolios = {k: v.copy() for k, v in portfolios.items()}

    if watch is None or watch.empty:
        watch = DEFAULT_WATCHLIST.copy()
    else:
        watch = watch.copy()

    return portfolios, watch

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
    save_label = "💾 Save to Google Sheets" if sheets_configured() else "💾 Save to portfolios.json"
    if st.button(save_label):
        if sheets_configured():
            saved_portfolios = save_portfolios_to_sheet(st.session_state["portfolios"])
            saved_watchlist = save_watchlist_to_sheet(st.session_state.get("watchlist", pd.DataFrame(columns=["Ticker"])))
            if saved_portfolios:
                msg = "Saved portfolios to Google Sheets."
                if saved_watchlist:
                    msg = "Saved portfolios & watchlist to Google Sheets."
                st.success(msg)
            else:
                st.error("Unable to save to Google Sheets. Check your Sheets secrets configuration.")
        else:
            blob = {
                "portfolios": {k: v.to_dict(orient="records") for k, v in st.session_state["portfolios"].items()},
                "watchlist": st.session_state["watchlist"].to_dict(orient="records"),
            }
            DATA_FILE.write_text(json.dumps(blob, indent=2))
            st.success("Saved locally to portfolios.json.")

# ---------- Query param / active selection ----------
# read ?p=<portfolio_name> if provided
def _get_query_param(key: str) -> str | None:
    """Return first value for ?key=..., handling both new & legacy Streamlit APIs."""
    try:
        raw = st.query_params.get(key)
    except Exception:
        try:
            raw = st.experimental_get_query_params().get(key)
        except Exception:
            raw = None
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if isinstance(raw, str):
        return unquote(raw)
    return None

requested = _get_query_param("p")

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
@@ -323,59 +527,62 @@ for name, df in st.session_state["portfolios"].items():
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
qp_val = _get_query_param("p")
if qp_val and qp_val in portfolio_names and qp_val != st.session_state["active_portfolio"]:
    st.session_state["active_portfolio"] = qp_val

# 3) Radio behaves like tabs; on change, update URL (no other code overwrites it)
def _on_pick_change():
    picked = st.session_state["_portfolio_picker"]
    st.session_state["active_portfolio"] = picked
    try:
        st.query_params.update({"p": picked})
    except Exception:
        st.experimental_set_query_params(p=picked)

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