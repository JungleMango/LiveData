"""Portfolio page with Google Sheets persistence (fallbacks to local JSON)."""

import json
import math
import re
import secrets
import time
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
COMPUTED_COLUMNS = [
    "Price",
    "Market Value",
    "Cost Basis",
    "P/L $",
    "P/L %",
    "Day %",
    "Weight %",
]
DISPLAY_COLUMNS = PORTFOLIO_HEADER + COMPUTED_COLUMNS
DEFAULT_PORTFOLIO_NAME = "Main Portfolio"
DEFAULT_PORTFOLIO_TEMPLATE = [{
    "Ticker": "QQQ",
    "Shares": 10.0,
    "Avg Cost": 420.0,
    "Currency": "USD",
    "Notes": "Sample",
    "Last Updated": "",
}]
SHEET_INDEX_TAB = "Portfolios_Index"
SHEET_TITLE_PREFIX = "PF"
PORTFOLIO_FILE = Path(__file__).resolve().parent.parent / "portfolios.json"

st.markdown(
    """
<style>
[data-testid="stDataEditor"] table tr td:nth-child(-n+5),
[data-testid="stDataEditor"] table tr th:nth-child(-n+5) {
  background-color: rgba(30,144,255,0.06);
}
</style>
""",
    unsafe_allow_html=True,
)

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
                r'(\"private_key\"\s*:\s*\")([^\"]+?)(\")',
                lambda m: m.group(1) + m.group(2).replace("\n", "\\n") + m.group(3),
                s,
                flags=re.S,
            )

        info = json.loads(_escape_pk_newlines(raw))

    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return gspread.authorize(creds)


@st.cache_resource(show_spinner=False)
def get_spreadsheet() -> gspread.Spreadsheet:
    client = get_sheet_client()
    return client.open_by_key(st.secrets["sheets"]["sheet_id"])


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
    suffix = secrets.token_hex(2)
    title = f"{SHEET_TITLE_PREFIX} - {base} {suffix}"
    return title[:100]


def _get_index_records() -> List[Dict[str, str]]:
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


def _ensure_default_portfolio_records() -> List[Dict[str, str]]:
    records = _get_index_records()
    if records:
        return records

    created = _create_portfolio_sheet(DEFAULT_PORTFOLIO_NAME)
    if created:
        df = pd.DataFrame(DEFAULT_PORTFOLIO_TEMPLATE)
        write_portfolio(DEFAULT_PORTFOLIO_NAME, df, prevent_empty=False)
    return _get_index_records()


def _get_portfolio_record(name: str) -> Optional[Dict[str, str]]:
    records = _ensure_default_portfolio_records()
    for record in records:
        if record["name"] == name:
            return record
    return None


def _create_portfolio_sheet(name: str, initial_rows: Optional[List[Dict[str, object]]] = None) -> bool:
    try:
        spreadsheet = get_spreadsheet()
        index_ws = _open_or_create_index_ws(spreadsheet)
        records = _get_index_records()
        if any(r["name"] == name for r in records):
            return False

        title = _generate_sheet_title(name)
        ws = spreadsheet.add_worksheet(title=title, rows=1000, cols=len(PORTFOLIO_HEADER))
        ws.update("A1", [PORTFOLIO_HEADER])
        index_ws.append_row([name, str(ws.id), title])

        if initial_rows:
            df = sanitize_base(pd.DataFrame(initial_rows))
            df = df.where(pd.notna(df), "")
            data = [PORTFOLIO_HEADER] + df.values.tolist()
            end_col = _col_letter(len(PORTFOLIO_HEADER))
            ws.update(f"A1:{end_col}{len(data)}", data)

        return True
    except Exception:
        return False


def _list_portfolios_sheets() -> List[str]:
    records = _ensure_default_portfolio_records()
    return sorted(record["name"] for record in records)


def _read_portfolio_sheets(name: str) -> pd.DataFrame:
    record = _get_portfolio_record(name)
    if not record:
        return sanitize_base(pd.DataFrame(columns=PORTFOLIO_HEADER))

    try:
        spreadsheet = get_spreadsheet()
        ws = spreadsheet.get_worksheet_by_id(int(record["sheet_id"]))
        values = ws.get_all_values()
    except Exception:
        return sanitize_base(pd.DataFrame(columns=PORTFOLIO_HEADER))

    if not values:
        return sanitize_base(pd.DataFrame(columns=PORTFOLIO_HEADER))

    header, *rows = values
    if not header:
        header = PORTFOLIO_HEADER
    df = pd.DataFrame(rows, columns=header)
    return sanitize_base(df)


def _write_portfolio_sheets(
    name: str,
    df: pd.DataFrame,
    prevent_empty: bool = True,
) -> Tuple[bool, pd.DataFrame]:
    record = _get_portfolio_record(name)
    if not record:
        created = _create_portfolio_sheet(name)
        if not created:
            st.warning("Unable to create Google Sheet tab for this portfolio.")
            return False, df
        record = _get_portfolio_record(name)
        if not record:
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
        spreadsheet = get_spreadsheet()
        ws = spreadsheet.get_worksheet_by_id(int(record["sheet_id"]))
        ws.clear()
        end_col = _col_letter(len(PORTFOLIO_HEADER))
        ws.update(f"A1:{end_col}{len(data)}", data)
    except Exception:
        st.warning("Failed to write portfolio to Google Sheets.")
        return False, df

    return True, sanitize_base(clean)


def _delete_portfolio_sheets(name: str) -> bool:
    records = _get_index_records()
    if len(records) <= 1:
        return False

    record = next((r for r in records if r["name"] == name), None)
    if not record:
        return False

    try:
        spreadsheet = get_spreadsheet()
        ws = spreadsheet.get_worksheet_by_id(int(record["sheet_id"]))
        spreadsheet.del_worksheet(ws)
        index_ws = _open_or_create_index_ws(spreadsheet)
        index_ws.delete_rows(record["row"])
        return True
    except Exception:
        return False


def _portfolio_store_path() -> Path:
    return PORTFOLIO_FILE


def _load_local_store() -> Dict[str, List[Dict[str, object]]]:
    path = _portfolio_store_path()
    if path.exists():
        try:
            data = json.loads(path.read_text())
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
    path = _portfolio_store_path()
    path.write_text(json.dumps(store, indent=2))


def _list_portfolios_local() -> List[str]:
    store = _load_local_store()
    return sorted(store.keys())


def _read_portfolio_local(name: str) -> pd.DataFrame:
    store = _load_local_store()
    rows = store.get(name, [])
    if not rows:
        return sanitize_base(pd.DataFrame(columns=PORTFOLIO_HEADER))
    return sanitize_base(pd.DataFrame(rows))


def _write_portfolio_local(
    name: str,
    df: pd.DataFrame,
    prevent_empty: bool = True,
) -> Tuple[bool, pd.DataFrame]:
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
    out = clean.where(pd.notna(clean), None).to_dict(orient="records")
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


def list_portfolios() -> List[str]:
    if sheets_configured():
        return _list_portfolios_sheets()
    return _list_portfolios_local()


def read_portfolio(name: str) -> pd.DataFrame:
    if sheets_configured():
        return _read_portfolio_sheets(name)
    return _read_portfolio_local(name)


def write_portfolio(
    name: str,
    df: pd.DataFrame,
    prevent_empty: bool = True,
) -> Tuple[bool, pd.DataFrame]:
    if sheets_configured():
        return _write_portfolio_sheets(name, df, prevent_empty=prevent_empty)
    return _write_portfolio_local(name, df, prevent_empty=prevent_empty)


def create_portfolio(name: str) -> bool:
    if sheets_configured():
        return _create_portfolio_sheet(name)
    return _create_portfolio_local(name)


def delete_portfolio(name: str) -> bool:
    if sheets_configured():
        return _delete_portfolio_sheets(name)
    return _delete_portfolio_local(name)


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
    clean = clean[clean["Ticker"] != ""].reset_index(drop=True)
    return clean
def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, str) and not value.strip():
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def build_display(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, float | None]]:
    base = df.reset_index(drop=True).copy()
    for col in COMPUTED_COLUMNS:
        if col not in base.columns:
            base[col] = pd.NA

    tickers: List[str] = []
    idxs: List[int] = []
    for idx, ticker in enumerate(base["Ticker"].tolist()):
        ticker = str(ticker).strip().upper()
        base.at[idx, "Ticker"] = ticker
        if ticker:
            tickers.append(ticker)
            idxs.append(idx)
@@ -324,161 +604,162 @@ def fetch_quotes(tickers: List[str]) -> pd.DataFrame:
        prev_close = prev_map.get(t)
        day_pct = None
        if price is not None and prev_close not in (None, 0) and not (
            isinstance(prev_close, float) and math.isnan(prev_close)
        ):
            day_pct = (price / prev_close - 1) * 100.0

        rows.append(
            {
                "Ticker": t,
                "Price": price,
                "Day %": day_pct,
                "Prev Close": prev_close,
                "Time": ts_now,
            }
        )

    return pd.DataFrame(rows)


# ============================
#              UI
# ============================
st.title("📂 Portfolios")

portfolio_names = list_portfolios()
pending_selection = st.session_state.pop("pending_selected_portfolio", None)
if pending_selection:
    st.session_state["selected_portfolio"] = pending_selection
if not portfolio_names:
    portfolio_names = [DEFAULT_PORTFOLIO_NAME]

selected_name = st.session_state.get("selected_portfolio")
if selected_name not in portfolio_names:
    st.session_state["selected_portfolio"] = portfolio_names[0]

sel_col, add_col, del_col = st.columns([3, 2, 2])
with sel_col:
    selected_name = st.selectbox("Select portfolio", portfolio_names, key="selected_portfolio")

with add_col:
    with st.form("add_portfolio_form", clear_on_submit=True):
        new_name = st.text_input(
            "New portfolio name",
            placeholder="e.g., Retirement",
            label_visibility="collapsed",
        )
        create = st.form_submit_button("➕ Add Portfolio", use_container_width=True)
        if create:
            candidate = new_name.strip()
            if not candidate:
                st.warning("Enter a name to create a portfolio.")
            elif candidate in portfolio_names:
                st.warning("A portfolio with that name already exists.")
            elif create_portfolio(candidate):
                st.session_state.pop(f"portfolio_data::{candidate}", None)
                st.session_state["pending_selected_portfolio"] = candidate
                st.session_state.pop("confirm_delete_target", None)
                st.rerun()
            else:
                st.warning("Unable to create the portfolio. Check your Google Sheet configuration.")

with del_col:
    delete_disabled = len(portfolio_names) <= 1
    if st.button(
        "🗑️ Delete Portfolio",
        use_container_width=True,
        disabled=delete_disabled,
    ):
        st.session_state["confirm_delete_target"] = selected_name

confirm_target = st.session_state.get("confirm_delete_target")
if confirm_target == selected_name:
    st.warning(f"Delete portfolio '{selected_name}'? This cannot be undone.")
    confirm_col, cancel_col = st.columns(2)
    with confirm_col:
        if st.button("Yes, delete", key="confirm_delete_btn", type="secondary"):
            if delete_portfolio(selected_name):
                st.session_state.pop(f"portfolio_data::{selected_name}", None)
                st.session_state.pop("confirm_delete_target", None)
                remaining = list_portfolios()
                if not remaining:
                    remaining = [DEFAULT_PORTFOLIO_NAME]
                st.session_state["selected_portfolio"] = remaining[0]
                st.rerun()
            else:
                st.warning("Unable to delete portfolio.")
    with cancel_col:
        if st.button("Cancel", key="cancel_delete_btn"):
            st.session_state.pop("confirm_delete_target", None)

info_col, toggle_col, interval_col = st.columns([2, 1, 1])
with info_col:
    if sheets_configured():
        st.caption("Edit holdings below. Changes persist to your Google Sheet when you save.")
    else:
        st.caption("Edit holdings below. Changes persist locally in `portfolios.json` when you save.")
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

session_key = f"portfolio_data::{selected_name}"
if session_key not in st.session_state:
    st.session_state[session_key] = read_portfolio(selected_name)

base_df = st.session_state[session_key]
display_df, totals = build_display(base_df)

edited_df = st.data_editor(
    display_df,
    num_rows="dynamic",
    use_container_width=True,
    hide_index=True,
    key=f"portfolio_editor::{selected_name}",
    column_config={
        "Ticker": st.column_config.TextColumn(help="e.g., QQQ, NVDA, AAPL"),
        "Shares": st.column_config.NumberColumn(format="%.4f", help="Can be fractional"),
        "Avg Cost": st.column_config.NumberColumn(format="%.4f"),
        "Currency": st.column_config.TextColumn(help="USD/CAD/etc"),
        "Notes": st.column_config.TextColumn(),
        "Last Updated": st.column_config.TextColumn(disabled=True),
        "Price": st.column_config.NumberColumn(format="%.2f", disabled=True),
        "Market Value": st.column_config.NumberColumn(format="%.2f", disabled=True),
        "Cost Basis": st.column_config.NumberColumn(format="%.2f", disabled=True),
        "P/L $": st.column_config.NumberColumn(format="%.2f", disabled=True),
        "P/L %": st.column_config.NumberColumn(format="%.2f%%", disabled=True),
        "Day %": st.column_config.NumberColumn(format="%.2f%%", disabled=True),
        "Weight %": st.column_config.NumberColumn(format="%.2f%%", disabled=True),
    },
)

updated_base = sanitize_base(edited_df[PORTFOLIO_HEADER])
if not updated_base.equals(base_df):
    st.session_state[session_key] = updated_base
    st.rerun()

save_col, _ = st.columns([1, 5])
with save_col:
    if st.button("💾 Save Portfolio", type="primary", use_container_width=True):
        success, saved_df = write_portfolio(selected_name, base_df)
        if success:
            st.session_state[session_key] = saved_df
            st.success("Saved portfolio ✅")
            st.rerun()

m1, m2, m3, m4 = st.columns(4)
fmt2 = lambda x: "" if x is None else f"{x:.2f}"
m1.metric("Total Market Value", fmt2(totals["total_mv"]))
m2.metric("Total Cost Basis", fmt2(totals["total_cb"]))
m3.metric("Total P/L $", fmt2(totals["total_pl"]))
pl_pct = totals["total_pl_pct"]
m4.metric("Total P/L %", "" if pl_pct is None else f"{pl_pct:.2f}%")

st.caption("Prices refresh on the selected interval. P/L uses the latest price against your Shares and Avg Cost.")
