import streamlit as st
import pandas as pd
import gspread
from google.oauth2 import service_account

st.set_page_config(page_title="Ticker Sheet Editor", layout="wide")
st.title("📈 Edit and Add Tickers")

# ---------- AUTH ----------
CREDS = service_account.Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ],
)
SHEET_ID = st.secrets["sheets"]["sheet_id"]
TAB_NAME = st.sidebar.text_input("Worksheet (tab) name", value="Portfolio")

# ---------- LOAD SHEET ----------
@st.cache_data(ttl=30)
def load_sheet(sheet_id: str, tab: str):
    """Return (df, header, row_numbers, ticker_col_idx)"""
    gc = gspread.authorize(CREDS)
    ws = gc.open_by_key(sheet_id).worksheet(tab)
    values = ws.get_all_values()
    if not values:
        return pd.DataFrame(), [], [], None

    header = [h.strip() for h in values[0]]
    data = values[1:]
    df = pd.DataFrame(data, columns=header)
    row_numbers = list(range(2, 2 + len(df)))

    try:
        ticker_col_idx = header.index("Ticker") + 1
    except ValueError:
        ticker_col_idx = None
    return df, header, row_numbers, ticker_col_idx

# ---------- UPDATE EXISTING TICKERS ----------
def update_ticker_cells(sheet_id: str, tab: str, row_numbers, ticker_col_idx: int, new_tickers: list[str]):
    gc = gspread.authorize(CREDS)
    ws = gc.open_by_key(sheet_id).worksheet(tab)
    requests = []
    for rnum, new_val in zip(row_numbers, new_tickers):
        rng = gspread.utils.rowcol_to_a1(rnum, ticker_col_idx)
        requests.append({"range": rng, "values": [[new_val]]})
    requests = [r for r in requests if r["values"][0][0] is not None]
    if requests:
        ws.batch_update(requests, value_input_option="USER_ENTERED")

# ---------- APPEND NEW ROWS ----------
def append_new_rows(sheet_id: str, tab: str, df_new: pd.DataFrame):
    gc = gspread.authorize(CREDS)
    ws = gc.open_by_key(sheet_id).worksheet(tab)
    rows_to_add = df_new.fillna("").values.tolist()
    ws.append_rows(rows_to_add, value_input_option="USER_ENTERED")

# ---------- MAIN APP ----------
df, header, row_numbers, ticker_col_idx = load_sheet(SHEET_ID, TAB_NAME)

if df.empty:
    st.warning(f"'{TAB_NAME}' is empty or not found.")
    st.stop()

# Ensure "Ticker" column exists
if "Ticker" not in df.columns:
    st.error("No 'Ticker' column found. Please add it to your Google Sheet first.")
    st.stop()

# Show editable table
st.caption("Edit existing Tickers or add new rows below ↓")
edited = st.data_editor(
    df,
    use_container_width=True,
    num_rows="dynamic",  # 👈 allows adding new rows
    hide_index=False,
)

# ---------- SAVE BUTTON ----------
if st.button("💾 Save Changes to Google Sheet", type="primary"):
    try:
        original_tickers = df["Ticker"].astype(str)
        edited_tickers = edited["Ticker"].astype(str)

        # Detect newly added rows (Streamlit adds NaN index for new rows)
        if len(edited) > len(df):
            new_rows = edited.iloc[len(df):].copy()
            new_rows = new_rows.fillna("")  # Replace NaN with blanks
        else:
            new_rows = pd.DataFrame(columns=df.columns)

        # Detect changed tickers
        changed_mask = (original_tickers != edited_tickers[: len(df)])
        changed_positions = [i for i, changed in enumerate(changed_mask.tolist()) if changed]

        # 1️⃣ Update existing tickers
        if changed_positions and ticker_col_idx:
            changed_rows = [row_numbers[i] for i in changed_positions]
            changed_vals = [edited_tickers.iloc[i] for i in changed_positions]
            update_ticker_cells(SHEET_ID, TAB_NAME, changed_rows, ticker_col_idx, changed_vals)
            st.success(f"Updated {len(changed_rows)} existing ticker(s).")

        # 2️⃣ Append new rows
        if not new_rows.empty:
            append_new_rows(SHEET_ID, TAB_NAME, new_rows)
            st.success(f"Appended {len(new_rows)} new row(s).")

        if not changed_positions and new_rows.empty:
            st.info("No changes detected.")

        st.toast("✅ Sheet updated successfully")
        st.cache_data.clear()

    except Exception as e:
        st.error(f"Save failed: {e}")

# ---------- REFRESH ----------
if st.button("🔄 Reload from Sheet"):
    st.cache_data.clear()
    st.rerun()
