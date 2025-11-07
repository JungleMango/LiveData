# 02_📂_Portfolios.py
# Portfolio page with Google Sheets persistence (fallbacks to local JSON).
# Optimized I/O, caching, and quote fetching.

from __future__ import annotations

import json
import math
import re
import time
import secrets as pysecrets
import concurrent.futures as cf
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st
import yfinance as yf
import gspread
from google.oauth2 import service_account

# ============================
#            CONFIG
# ============================
st.set_page_config(
    page_title="Portfolios",
    page_icon="📂",
    layout="wide",
    initial_sidebar_state="expanded",
)

PORTFOLIO_HEADER = ["Ticker", "Shares", "Avg Cost", "Currency", "Notes", "Last Updated"]
COMPUTED_COLUMNS = ["Price", "Market Value", "Cost Basis", "P/L $", "P/L %", "Day %", "Weight %"]
DISPLAY_COLUMNS = PORTFOLIO_HEADER + COMPUTED_COLUMNS

DEFAULT_PORTFOLIO_NAME = "Main Portfolio"
DEFAULT_PORTFOLIO_TEMPLATE = [{
    "Ticker": "QQQ", "Shares": 10.0, "Avg Cost": 420.0, "Currency": "USD", "Notes": "Sample", "Last Updated": ""
}]

SHEET_INDEX_TAB = "Portfolios_Index"
SHEET_TITLE_PREFIX = "PF"
PORTFOLIO_FILE = Path(__file__).resolve().parent.parent / "portfolios.json"

st.markdown("""
<style>
[data-testid="stDataEditor"] table tr td:nth-child(-n+5),
[data-testid="stDataEditor"] table tr th:nth-child(-n+5) {
  background-color: rgba(30,144,255,0.06);
}
</style>
""", unsafe_allow_html=True)

# ============================
#        SHEETS / STORAGE
# ============================
def sheets_configured() -> bool:
    try:
        s = st.secrets["sheets"]
        return bool(s.get("sheet_id")) and bool(s.get("service_account"))
    except Exception:
        return False

def _assert_sheets_secrets() -> None:
    if "sheets" not in st.secrets:
        st.error("Missing [sheets] configuration (App → Settings → Secrets).")
        st.stop()
    for key in ("sheet_id", "service_account"):
        if key not in st.secrets["sheets"]:
            st.error(f"Missing key in [sheets]: {key}")
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
def get_spreadsheet() -> gspread.Spreadsheet:
    return get_sheet_client().open_by_key(st.secrets["sheets"]["sheet_id"])

def _open_or_create_index_ws(spreadsheet: gspread.Spreadsheet) -> gspread.Worksheet:
    try:
        ws = spreadsheet.worksheet(SHEET_INDEX_TAB)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=SHEET_INDEX_TAB, rows=1000, cols=3)
        ws.update("A1:C1", [["Name", "SheetID", "Title"]])
        return ws
    header = ws.row_values(1)
    if header[:3] != ["Name", "SheetID", "Title"]:
        ws.update("A1:C1", [["Name", "SheetID", "Title"]])
    return ws

def _col_letter(idx: int) -> str:
    # 1 -> A
    result = ""
    n = idx
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result or "A"

def _generate_sheet_title(name: str) -> str:
    cleaned = re.sub(r"[\\/:?*\[\]]", " ", name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    base = cleaned or "Portfolio"
    suffix = pysecrets.token_hex(2)
    return f"{SHEET_TITLE_PREFIX} - {base} {suffix}"[:100]

@st.cache_data(ttl=60, show_spinner=False)
def _get_index_records_cached(dummy: int = 0) -> List[Dict[str, str]]:
    """Cached index listing. Invalidate by calling st.cache_data.clear() after create/delete."""
    try:
        spreadsheet = get_spreadsheet()
        ws = _open_or_create_index_ws(spreadsheet)
        values = ws.get_all_values()
    except Exception:
        return []
    if not values:
        return []
    header, *rows = values
    records: List[Dict[str, str]] = []
    for idx, row in enumerate(rows, start=2):
        if not row:
            continue
        name = row[0].strip() if len(row) > 0 else ""
        sheet_id = row[1].strip() if len(row) > 1 else ""
        title = row[2].strip() if len(row) > 2 else ""
        if not name:
            continue
        records.append({"name": name, "sheet_id": sheet_id, "title": title, "row": idx})
    return records

def _get_index_records() -> List[Dict[str, str]]:
    return _get_index_records_cached(0)

def _ensure_default_portfolio_records() -> List[Dict[str, str]]:
    recs = _get_index_records()
    if recs:
        return recs
    if _create_portfolio_sheet(DEFAULT_PORTFOLIO_NAME):
        df = pd.DataFrame(DEFAULT_PORTFOLIO_TEMPLATE)
        _ = _write_portfolio_sheets(DEFAULT_PORTFOLIO_NAME, df, prevent_empty=False)
        st.cache_data.clear()  # invalidate index cache
    return _get_index_records()

def _get_portfolio_record(name: str) -> Optional[Dict[str, str]]:
    for r in _ensure_default_portfolio_records():
        if r["name"] == name:
            return r
    return None

def _create_portfolio_sheet(name: str, initial_rows: Optional[List[Dict[str, object]]] = None) -> bool:
    try:
        spreadsheet = get_spreadsheet()
        index_ws = _open_or_create_index_ws(spreadsheet)
        if any(r["name"] == name for r in _get_index_records()):
            return False
        title = _generate_sheet_title(name)
        ws = spreadsheet.add_worksheet(title=title, rows=1000, cols=len(PORTFOLIO_HEADER))
        ws.update("A1", [PORTFOLIO_HEADER])
        index_ws.append_row([name, str(ws.id), title])
        if initial_rows:
            df = sanitize_base(pd.DataFrame(initial_rows))
            out = df.where(pd.notna(df), "")
            data = [PORTFOLIO_HEADER] + out.values.tolist()
            end_col = _col_letter(len(PORTFOLIO_HEADER))
            ws.update(f"A1:{end_col}{len(data)}", data)
        st.cache_data.clear()
        return True
    except Exception:
        return False

def _list_portfolios_sheets() -> List[str]:
    return sorted(r["name"] for r in _ensure_default_portfolio_records())

def _read_portfolio_sheets(name: str) -> pd.DataFrame:
    r = _get_portfolio_record(name)
    if not r:
        return sanitize_base(pd.DataFrame(columns=PORTFOLIO_HEADER))
    try:
        ws = get_spreadsheet().get_worksheet_by_id(int(r["sheet_id"]))
        values = ws.get_all_values()
    except Exception:
        return sanitize_base(pd.DataFrame(columns=PORTFOLIO_HEADER))
    if not values:
        return sanitize_base(pd.DataFrame(columns=PORTFOLIO_HEADER))
    header, *rows = values
    if not header:
        header = PORTFOLIO_HEADER
    return sanitize_base(pd.DataFrame(rows, columns=header))

def _write_portfolio_sheets(name: str, df: pd.DataFrame, prevent_empty: bool = True) -> Tuple[bool, pd.DataFrame]:
    r = _get_portfolio_record(name)
    if not r:
        if not _create_portfolio_sheet(name):
            st.warning("Unable to create Google Sheet tab for this portfolio.")
            return False, df
        r = _get_portfolio_record(name)
        if not r:
            return False, df

    clean = _normalize(df)
    if clean.empty:
        if prevent_empty:
            st.warning("Skipped save: portfolio is empty (won’t overwrite the sheet).")
            return False, df
        clean = sanitize_base(pd.DataFrame(columns=PORTFOLIO_HEADER))

    ts = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M:%S UTC")
    if not clean.empty:
        clean.loc[:, "Last Updated"] = ts

    out = clean.where(pd.notna(clean), "")
    data = [PORTFOLIO_HEADER] + out.values.tolist() if not out.empty else [PORTFOLIO_HEADER]

    try:
        ws = get_spreadsheet().get_worksheet_by_id(int(r["sheet_id"]))
        ws.clear()
        end_col = _col_letter(len(PORTFOLIO_HEADER))
        ws.update(f"A1:{end_col}{len(data)}", data)
        return True, sanitize_base(clean)
    except Exception:
        st.warning("Failed to write portfolio to Google Sheets.")
        return False, df

def _delete_portfolio_sheets(name: str) -> bool:
    recs = _get_index_records()
    if len(recs) <= 1:
        return False
    r = next((x for x in recs if x["name"] == name), None)
    if not r:
        return False
    try:
        ss = get_spreadsheet()
        ws = ss.get_worksheet_by_id(int(r["sheet_id"]))
        ss.del_worksheet(ws)
        idx_ws = _open_or_create_index_ws(ss)
        idx_ws.delete_rows(r["row"])
        st.cache_data.clear()
        return True
    except Exception:
        return False

# ---------- Local JSON fallback ----------
def _portfolio_store_path() -> Path:
    return PORTFOLIO_FILE

def _load_local_store() -> Dict[str, List[Dict[str, object]]]:
    p = _portfolio_store_path()
    if p.exists():
        try:
            data = json.loads(p.read_text())
            if isinstance(data, dict):
                cleaned: Dict[str, List[Dict[str, object]]] = {}
                for name, rows in data.items():
                    if isinstance(name, str) and isinstance(rows, list):
                        cleaned[name] = [r for r in rows if isinstance(r, dict)]
                if cleaned:
                    return cleaned
        except json.JSONDecodeError:
            pass
    default = {DEFAULT_PORTFOLIO_NAME: DEFAULT_PORTFOLIO_TEMPLATE}
    _save_local_store(default)
    return default

def _save_local_store(store: Dict[str, List[Dict[str, object]]]) -> None:
    _portfolio_store_path().write_text(json.dumps(store, indent=2))

def _list_portfolios_local() -> List[str]:
    return sorted(_load_local_store().keys())

def _read_portfolio_local(name: str) -> pd.DataFrame:
    rows = _load_local_store().get(name, [])
    if not rows:
        return sanitize_base(pd.DataFrame(columns=PORTFOLIO_HEADER))
    return sanitize_base(pd.DataFrame(rows))

def _write_portfolio_local(name: str, df: pd.DataFrame, prevent_empty: bool = True) -> Tuple[bool, pd.DataFrame]:
    store = _load_local_store()
    clean = _normalize(df)
    if clean.empty:
        if prevent_empty:
            st.warning("Skipped save: portfolio is empty (won’t overwrite saved data).")
            return False, df
        store[name] = []
        _save_local_store(store)
        return True, sanitize_base(pd.DataFrame(columns=PORTFOLIO_HEADER))
    ts = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M:%S UTC")
    clean.loc[:, "Last Updated"] = ts
    out = clean.where(pd.notna(clean), None).to_dict("records")
    store[name] = out
    _save_local_store(store)
    return True, sanitize_base(clean)

def _create_portfolio_local(name: str) -> bool:
    store = _load_local_store()
    if name in store:
        return False
    store[name] = []
    _save_local_store(store)
    return True

def _delete_portfolio_local(name: str) -> bool:
    store = _load_local_store()
    if name not in store or len(store) <= 1:
        return False
    store.pop(name, None)
    _save_local_store(store)
    return True

# ---------- Strategy multiplexer ----------
def list_portfolios() -> List[str]:
    return _list_portfolios_sheets() if sheets_configured() else _list_portfolios_local()

def read_portfolio(name: str) -> pd.DataFrame:
    return _read_portfolio_sheets(name) if sheets_configured() else _read_portfolio_local(name)

def write_portfolio(name: str, df: pd.DataFrame, prevent_empty: bool = True) -> Tuple[bool, pd.DataFrame]:
    return (_write_portfolio_sheets if sheets_configured() else _write_portfolio_local)(
        name, df, prevent_empty
    )

def create_portfolio(name: str) -> bool:
    return _create_portfolio_sheet(name) if sheets_configured() else _create_portfolio_local(name)

def delete_portfolio(name: str) -> bool:
    return _delete_portfolio_sheets(name) if sheets_configured() else _delete_portfolio_local(name)

# ============================
#          SANITIZERS
# ============================
def sanitize_base(df: pd.DataFrame) -> pd.DataFrame:
    base = df.copy()
    for col in PORTFOLIO_HEADER:
        if col not in base.columns:
            base[col] = "" if col not in ("Shares", "Avg Cost") else pd.NA
    base = base[PORTFOLIO_HEADER].reset_index(drop=True)
    base["Ticker"] = base["Ticker"].fillna("").astype(str).str.strip().str.upper()
    base["Currency"] = base["Currency"].fillna("").astype(str).str.strip().str.upper()
    base["Notes"] = base["Notes"].fillna("").astype(str)
    base["Last Updated"] = base["Last Updated"].fillna("").astype(str)
    base["Shares"] = pd.to_numeric(base["Shares"], errors="coerce")
    base["Avg Cost"] = pd.to_numeric(base["Avg Cost"], errors="coerce")
    return base

def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    clean = sanitize_base(df)
    return clean[clean["Ticker"] != ""].reset_index(drop=True)

# ============================
#         QUOTE ENGINE
# ============================
def _threaded_prev_close(tickers: List[str]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    def one(t: str):
        try:
            fi = yf.Ticker(t).fast_info
            pc = fi.get("previous_close", None)
            if pc is not None:
                out[t] = float(pc)
        except Exception:
            pass
    if not tickers:
        return out
    with cf.ThreadPoolExecutor(max_workers=min(8, max(2, len(tickers)))) as ex:
        list(ex.map(one, tickers))
    return out

@st.cache_data(ttl=45, show_spinner=False)
def fetch_quotes(tickers: List[str]) -> pd.DataFrame:
    tickers = [t.strip().upper() for t in tickers if isinstance(t, str) and t.strip()]
    tickers = sorted(set(tickers))
    if not tickers:
        return pd.DataFrame(columns=["Ticker", "Price", "Day %", "Prev Close", "Time"])
    try:
        hist = yf.download(tickers=tickers, period="1d", interval="1m",
                           group_by="ticker", auto_adjust=False, progress=False)
    except Exception:
        hist = pd.DataFrame()
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

def build_display(base_df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Optional[float]]]:
    base = sanitize_base(base_df)
    # Ensure computed columns exist
    for c in COMPUTED_COLUMNS:
        if c not in base.columns:
            base[c] = pd.NA

    tickers = [t for t in base["Ticker"].tolist() if t]
    qdf = fetch_quotes(tickers) if tickers else pd.DataFrame(columns=["Ticker", "Price", "Day %", "Prev Close", "Time"])
    merged = base.merge(qdf, on="Ticker", how="left")

    # vectorized calcs
    for col in ("Price", "Shares", "Avg Cost"):
        merged[col] = pd.to_numeric(merged[col], errors="coerce")

    merged["Market Value"] = merged["Price"] * merged["Shares"]
    merged["Cost Basis"]   = merged["Avg Cost"] * merged["Shares"]
    merged["P/L $"]        = merged["Market Value"] - merged["Cost Basis"]
    merged["P/L %"]        = (merged["P/L $"] / merged["Cost Basis"]) * 100

    total_mv = float(pd.to_numeric(merged["Market Value"], errors="coerce").sum())
    total_cb = float(pd.to_numeric(merged["Cost Basis"], errors="coerce").sum())
    total_pl = total_mv - total_cb
    total_pl_pct = (total_pl / total_cb * 100) if total_cb else None
    merged["Weight %"] = (merged["Market Value"] / total_mv * 100) if total_mv else 0.0

    display = merged[DISPLAY_COLUMNS].copy()
    totals = {"total_mv": total_mv, "total_cb": total_cb, "total_pl": total_pl, "total_pl_pct": total_pl_pct}
    return display, totals

# ============================
#              UI
# ============================
st.title("📂 Portfolios")

# Selection / create / delete
portfolio_names = list_portfolios() or [DEFAULT_PORTFOLIO_NAME]
selected_name = st.session_state.get("selected_portfolio")
if selected_name not in portfolio_names:
    selected_name = portfolio_names[0]
    st.session_state["selected_portfolio"] = selected_name

sel_col, add_col, del_col = st.columns([3, 2, 2])
with sel_col:
    selected_name = st.selectbox("Select portfolio", portfolio_names, key="selected_portfolio")

with add_col:
    with st.form("add_portfolio_form", clear_on_submit=True):
        new_name = st.text_input("New portfolio name", placeholder="e.g., Retirement", label_visibility="collapsed")
        create_btn = st.form_submit_button("➕ Add Portfolio", use_container_width=True)
        if create_btn:
            candidate = new_name.strip()
            if not candidate:
                st.warning("Enter a name to create a portfolio.")
            elif candidate in portfolio_names:
                st.warning("A portfolio with that name already exists.")
            elif create_portfolio(candidate):
                st.cache_data.clear()
                st.session_state["selected_portfolio"] = candidate
                st.success("Portfolio created ✅")
                st.rerun()
            else:
                st.warning("Unable to create the portfolio. Check your configuration.")

with del_col:
    if st.button("🗑️ Delete Portfolio", use_container_width=True, disabled=len(portfolio_names) <= 1):
        st.session_state["confirm_delete_target"] = selected_name

target = st.session_state.get("confirm_delete_target")
if target == selected_name:
    st.warning(f"Delete portfolio '{selected_name}'? This cannot be undone.")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Yes, delete", key="confirm_delete_btn", type="secondary"):
            if delete_portfolio(selected_name):
                st.cache_data.clear()
                remaining = list_portfolios() or [DEFAULT_PORTFOLIO_NAME]
                st.session_state.pop("confirm_delete_target", None)
                st.session_state["selected_portfolio"] = remaining[0]
                st.success("Deleted ✅")
                st.rerun()
            else:
                st.warning("Unable to delete portfolio.")
    with c2:
        if st.button("Cancel", key="cancel_delete_btn"):
            st.session_state.pop("confirm_delete_target", None)

# Refresh controls
info_col, toggle_col, interval_col = st.columns([2, 1, 1])
with info_col:
    st.caption("Changes persist to Google Sheets" if sheets_configured()
               else "Changes persist locally in `portfolios.json`.")
with toggle_col:
    auto_refresh = st.toggle("Auto-refresh", value=True, help="Refresh quotes periodically")
with interval_col:
    interval = st.selectbox("Refresh Interval (sec)", [15, 30, 45, 60], index=1)

if auto_refresh:
    now = time.time()
    last = st.session_state.get("_portfolio_last_refresh", 0.0)
    if now - last >= interval:
        st.session_state["_portfolio_last_refresh"] = now
        st.rerun()

# Load session copy once per portfolio
session_key = f"portfolio_data::{selected_name}"
if session_key not in st.session_state:
    st.session_state[session_key] = read_portfolio(selected_name)

base_df: pd.DataFrame = st.session_state[session_key]
display_df, totals = build_display(base_df)

# Editor (editable base columns; computed columns disabled)
edited_df = st.data_editor(
    display_df,
    num_rows="dynamic",
    use_container_width=True,
    hide_index=True,
    key=f"portfolio_editor::{selected_name}",
    column_config={
        "Ticker":        st.column_config.TextColumn(help="e.g., QQQ, NVDA, AAPL"),
        "Shares":        st.column_config.NumberColumn(format="%.4f", help="Can be fractional"),
        "Avg Cost":      st.column_config.NumberColumn(format="%.4f"),
        "Currency":      st.column_config.TextColumn(help="USD/CAD/etc"),
        "Notes":         st.column_config.TextColumn(),
        "Last Updated":  st.column_config.TextColumn(disabled=True),
        "Price":         st.column_config.NumberColumn(format="%.2f",  disabled=True),
        "Market Value":  st.column_config.NumberColumn(format="%.2f",  disabled=True),
        "Cost Basis":    st.column_config.NumberColumn(format="%.2f",  disabled=True),
        "P/L $":         st.column_config.NumberColumn(format="%.2f",  disabled=True),
        "P/L %":         st.column_config.NumberColumn(format="%.2f%%",disabled=True),
        "Day %":         st.column_config.NumberColumn(format="%.2f%%",disabled=True),
        "Weight %":      st.column_config.NumberColumn(format="%.2f%%",disabled=True),
    },
)

# If user edited the editable columns, update the session base and rebuild display immediately (no rerun needed)
updated_base = sanitize_base(edited_df[PORTFOLIO_HEADER])
if not updated_base.equals(base_df):
    st.session_state[session_key] = updated_base
    base_df = updated_base
    display_df, totals = build_display(base_df)

# Save
save_col, _ = st.columns([1, 5])
with save_col:
    if st.button("💾 Save Portfolio", type="primary", use_container_width=True):
        ok, saved_df = write_portfolio(selected_name, base_df)
        if ok:
            st.session_state[session_key] = saved_df
            st.success("Saved portfolio ✅")
            # no rerun; we just updated session state

# Totals
m1, m2, m3, m4 = st.columns(4)
_fmt2 = lambda x: "" if (x is None or (isinstance(x, float) and math.isnan(x))) else f"{x:.2f}"
m1.metric("Total Market Value", _fmt2(totals["total_mv"]))
m2.metric("Total Cost Basis", _fmt2(totals["total_cb"]))
m3.metric("Total P/L $", _fmt2(totals["total_pl"]))
pl_pct = totals["total_pl_pct"]
m4.metric("Total P/L %", "" if (pl_pct is None or (isinstance(pl_pct, float) and math.isnan(pl_pct))) else f"{pl_pct:.2f}%")

st.caption("Prices refresh on the selected interval. P/L uses the latest price against your Shares and Avg Cost.")
