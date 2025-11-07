# pages/04_🔎_Stock_Analysis.py
import streamlit as st
import pandas as pd
import gspread
from google.oauth2 import service_account

st.set_page_config(page_title="Sheet Editor (Ticker-only)", layout="wide")
st.title("✏️ Edit only the Ticker column")

# ---- Auth (uses your Streamlit Secrets) ----
CREDS = service_account.Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ],
)
SHEET_ID = st.secrets["sheets"]["sheet_id"]
TAB_NAME = st.sidebar.text_input("Worksheet (tab) name", value="Portfolio")

@st.cache_data(ttl=30)
def load_sheet(sheet_id: str, tab: str):
    """Return (df, header, row_numbers, ticker_col_idx)"""
    gc = gspread.authorize(CREDS)
    ws = gc.open_by_key(sheet_id).worksheet(tab)

    # Grab raw values to preserve row numbers and header order
    values = ws.get_all_values()  # list[list]
    if not values:
        return pd.DataFrame(), [], [], None

    header = values[0]
    data = values[1:]

    # DataFrame with exact header order
    df = pd.DataFrame(data, columns=header)

    # Track sheet row numbers (2..n+1) to target precise cells on save
    row_numbers = list(range(2, 2 + len(df)))

    # Find Ticker column index (1-based for Sheets)
    try:
        ticker_col_idx = header.index("Ticker") + 1
    except ValueError:
        ticker_col_idx = None

    # Clean headers (strip) and keep original header list for positions
    df.columns = [c.strip() for c in df.columns]

    return df, header, row_numbers, ticker_col_idx

def update_ticker_cells(sheet_id: str, tab: str, row_numbers, ticker_col_idx: int, new_tickers: list[str]):
    """Batch update only the Ticker column cells that changed."""
    gc = gspread.authorize(CREDS)
    ws = gc.open_by_key(sheet_id).worksheet(tab)

    # Build A1 ranges for the Ticker column for all rows
    # Example: if ticker_col_idx=1 → A2:A{n}, but we need per-row updates to skip unchanged rows.
    # We'll use batch_update with one range per changed row.
    requests = []
    for rnum, new_val in zip(row_numbers, new_tickers):
        # Single-cell range like "A2"
        rng = gspread.utils.rowcol_to_a1(rnum, ticker_col_idx)
        requests.append({"range": rng, "values": [[new_val]]})
    # Execute in batches to avoid rate limits
    # Filter out None values just in case
    requests = [req for req in requests if req["values"][0][0] is not None]
    if not requests:
        return
    ws.batch_update(requests, value_input_option="USER_ENTERED")

# ---- Load ----
df, header, row_numbers, ticker_col_idx = load_sheet(SHEET_ID, TAB_NAME)
if df.empty:
    st.warning("Sheet/tab is empty or not found.")
    st.stop()
if ticker_col_idx is None:
    st.error("No 'Ticker' column found in the sheet header. Please add a 'Ticker' column.")
    st.stop()

st.caption(f"Editing only **Ticker** in tab **{TAB_NAME}** | Sheet: `{SHEET_ID}`")

# ---- Make only Ticker editable in the UI ----
cols = list(df.columns)
disabled_cols = [c for c in cols if c != "Ticker"]

edited = st.data_editor(
    df,
    use_container_width=True,
    num_rows="fixed",  # keep row count stable (change to "dynamic" if you want add/remove)
    disabled=disabled_cols,  # everything disabled except Ticker
    column_config={
        c: st.column_config.TextColumn(disabled=True) for c in disabled_cols
    } | {
        "Ticker": st.column_config.TextColumn(help="Edit only this column; other columns are read-only")
    },
    hide_index=False,
)

# ---- Save button (only writes Ticker changes) ----
if st.button("💾 Save Ticker changes to Google Sheets", type="primary"):
    try:
        # Compare original vs edited Ticker column
        original_tickers = df.get("Ticker", pd.Series(index=df.index, dtype=str)).astype(str)
        new_tickers = edited.get("Ticker", pd.Series(index=edited.index, dtype=str)).astype(str)

        # Determine which positions changed
        changed_mask = (original_tickers != new_tickers)
        changed_positions = [i for i, changed in enumerate(changed_mask.tolist()) if changed]

        if not changed_positions:
            st.info("No Ticker changes detected.")
        else:
            # Build per-row updates only for changed rows
            changed_rows = [row_numbers[i] for i in changed_positions]
            changed_vals = [new_tickers.iloc[i] for i in changed_positions]

            # Batch update only changed Ticker cells
            # (we’ll pass lists aligned to changed_rows)
            gc = gspread.authorize(CREDS)
            ws = gc.open_by_key(SHEET_ID).worksheet(TAB_NAME)

            requests = []
            for rnum, val in zip(changed_rows, changed_vals):
                rng = gspread.utils.rowcol_to_a1(rnum, ticker_col_idx)
                requests.append({"range": rng, "values": [[val]]})
            ws.batch_update(requests, value_input_option="USER_ENTERED")

            st.success(f"Updated Ticker in {len(changed_rows)} row(s).")
            st.toast("Ticker changes saved.", icon="✅")
            st.cache_data.clear()
    except Exception as e:
        st.error(f"Save failed: {e}")

# Optional: reload button
if st.button("🔄 Reload from Google Sheets"):
    st.cache_data.clear()
    st.rerun()
