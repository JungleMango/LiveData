
# Live Portfolio Tracker — local JSON persistence + optimized quotes

import json
import math
import time
import concurrent.futures as cf
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import streamlit as st
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
#      LOCAL PORTFOLIO I/O
# ============================
def _portfolio_store_path() -> Path:
    return PORTFOLIO_FILE


def _load_portfolio_store() -> Dict[str, List[Dict[str, object]]]:
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
    _save_portfolio_store(default)
    return default


def _save_portfolio_store(store: Dict[str, List[Dict[str, object]]]) -> None:
    path = _portfolio_store_path()
    path.write_text(json.dumps(store, indent=2))


def list_portfolios(store: Dict[str, List[Dict[str, object]]]) -> List[str]:
    return sorted(store.keys())


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


def read_portfolio(name: str, store: Dict[str, List[Dict[str, object]]]) -> pd.DataFrame:
    rows = store.get(name, [])
    if not rows:
        return sanitize_base(pd.DataFrame(columns=PORTFOLIO_HEADER))
    return sanitize_base(pd.DataFrame(rows))


def write_portfolio(
    name: str,
    df: pd.DataFrame,
    store: Dict[str, List[Dict[str, object]]],
    prevent_empty: bool = True,
) -> Tuple[bool, pd.DataFrame]:
    clean = _normalize(df)
    if clean.empty:
        if prevent_empty:
            st.warning("Skipped save: portfolio is empty (won’t overwrite saved data).")
            return False, df
        store[name] = []
        _save_portfolio_store(store)
        return True, sanitize_base(pd.DataFrame(columns=PORTFOLIO_HEADER))

    ts = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M:%S UTC")
    clean.loc[:, "Last Updated"] = ts
    out = clean.where(pd.notna(clean), None).to_dict(orient="records")
    store[name] = out
    _save_portfolio_store(store)
    return True, sanitize_base(clean)


def create_portfolio(name: str, store: Dict[str, List[Dict[str, object]]]) -> bool:
    if name in store:
        return False
    store[name] = []
    _save_portfolio_store(store)
    return True


def delete_portfolio(name: str, store: Dict[str, List[Dict[str, object]]]) -> bool:
    if name not in store or len(store) <= 1:
        return False
    store.pop(name, None)
    _save_portfolio_store(store)
    return True


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
        else:
            for col in COMPUTED_COLUMNS:
                base.at[idx, col] = None

    quotes = fetch_quotes(tickers)
    quote_map: Dict[str, Dict[str, float | None]] = {
        row["Ticker"]: row for row in quotes.to_dict(orient="records")
    }

    price_list: List[float | None] = [None] * len(base)
    mv_list: List[float | None] = [None] * len(base)
    cb_list: List[float | None] = [None] * len(base)
    pl_list: List[float | None] = [None] * len(base)
    pl_pct_list: List[float | None] = [None] * len(base)
    day_pct_list: List[float | None] = [None] * len(base)

    for idx, ticker in zip(idxs, tickers):
        q = quote_map.get(ticker, {})
        price = _to_float(q.get("Price")) if isinstance(q, dict) else None
        shares = _to_float(base.at[idx, "Shares"])
        avg_cost = _to_float(base.at[idx, "Avg Cost"])

        market_value = price * shares if price is not None and shares is not None else None
        cost_basis = avg_cost * shares if avg_cost is not None and shares is not None else None
        pl = (
            market_value - cost_basis
            if market_value is not None and cost_basis is not None
            else None
        )
        pl_pct = (
            (pl / cost_basis) * 100.0
            if pl is not None and cost_basis not in (None, 0)
            else None
        )

        day_pct = _to_float(q.get("Day %")) if isinstance(q, dict) else None

        price_list[idx] = price
        mv_list[idx] = market_value
        cb_list[idx] = cost_basis
        pl_list[idx] = pl
        pl_pct_list[idx] = pl_pct
        day_pct_list[idx] = day_pct

    total_mv = float(sum(v for v in mv_list if isinstance(v, (int, float))))
    total_cb = float(sum(v for v in cb_list if isinstance(v, (int, float))))
    total_pl = total_mv - total_cb
    total_pl_pct = (total_pl / total_cb * 100.0) if total_cb else None

    weight_pct_list: List[float | None] = [None] * len(base)
    if total_mv:
        for idx, mv in enumerate(mv_list):
            if mv not in (None, 0):
                weight_pct_list[idx] = (mv / total_mv) * 100.0

    for col, values in (
        ("Price", price_list),
        ("Market Value", mv_list),
        ("Cost Basis", cb_list),
        ("P/L $", pl_list),
        ("P/L %", pl_pct_list),
        ("Day %", day_pct_list),
        ("Weight %", weight_pct_list),
    ):
        base[col] = values

    display = base.reindex(columns=DISPLAY_COLUMNS)
    display = display.where(pd.notna(display), None)
    return display, {
        "total_mv": total_mv,
        "total_cb": total_cb,
        "total_pl": total_pl,
        "total_pl_pct": total_pl_pct,
    }


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

    if not tickers:
        return out

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

    try:
        hist = yf.download(
            tickers=tickers,
            period="1d",
            interval="1m",
            group_by="ticker",
            auto_adjust=False,
            progress=False,
        )
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

store = _load_portfolio_store()
portfolio_names = list_portfolios(store)
if not portfolio_names:
    store = _load_portfolio_store()
    portfolio_names = list_portfolios(store)

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
            elif create_portfolio(candidate, store):
                st.session_state.pop(f"portfolio_data::{candidate}", None)
                st.session_state["selected_portfolio"] = candidate
                st.session_state.pop("confirm_delete_target", None)
                st.rerun()

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
            if delete_portfolio(selected_name, store):
                st.session_state.pop(f"portfolio_data::{selected_name}", None)
                st.session_state.pop("confirm_delete_target", None)
                remaining = list_portfolios(store)
                if not remaining:
                    refreshed = _load_portfolio_store()
                    remaining = list_portfolios(refreshed)
                    store = refreshed
                st.session_state["selected_portfolio"] = remaining[0]
                st.rerun()
            else:
                st.warning("Unable to delete portfolio.")
    with cancel_col:
        if st.button("Cancel", key="cancel_delete_btn"):
            st.session_state.pop("confirm_delete_target", None)

info_col, toggle_col, interval_col = st.columns([2, 1, 1])
with info_col:
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
    st.session_state[session_key] = read_portfolio(selected_name, store)

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
        success, saved_df = write_portfolio(selected_name, base_df, store)
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