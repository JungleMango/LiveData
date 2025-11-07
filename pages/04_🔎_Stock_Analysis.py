# pages/04_🔎_Stock_Analysis.py  (or any page)
import streamlit as st
import pandas as pd
import gspread
from google.oauth2 import service_account

st.set_page_config(page_title="Sheet Editor", layout="wide")
st.title("✏️ Edit Google Sheet in Streamlit")

# ---- Auth (uses your Secrets from Streamlit Cloud) ----
CREDS = service_account.Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ],
)
SHEET_ID = st.secrets["sheets"]["sheet_id"]           # from your [sheets] block
TAB_NAME = st.sidebar.text_input("Worksheet (tab) name", value="Watchlist")

@st.cache_data(ttl=30)
def load_sheet(sheet_id: str, tab: str) -> pd.DataFrame:
    gc = gspread.authorize(CREDS)
    ws = gc.open_by_key(sheet_id).worksheet(tab)
    rows = ws.get_all_records()
    df = pd.DataFrame(rows)
    return df

def save_sheet(sheet_id: str, tab: str, df: pd.DataFrame) -> None:
    """Overwrite the sheet (headers + all rows) with df."""
    gc = gspread.authorize(CREDS)
    ws = gc.open_by_key(sheet_id).worksheet(tab)

    # Replace NaN with empty strings to avoid API issues
    out = df.copy()
    out = out.fillna("")

    # Convert to list-of-lists with header row first
    values = [list(out.columns)] + out.astype(str).values.tolist()

    # Clear then write starting at A1
    ws.clear()
    ws.update("A1", values)

# ---- Load ----
try:
    df = load_sheet(SHEET_ID, TAB_NAME)
except Exception as e:
    st.error(f"Could not load sheet/tab: {e}")
    st.stop()

st.caption(f"Editing tab: **{TAB_NAME}** from Sheet ID: `{SHEET_ID}`")
st.write("Tip: you can add/remove rows in the editor; columns should stay consistent.")

# ---- Editable table ----
edited = st.data_editor(
    df,
    num_rows="dynamic",          # allow adding rows
    use_container_width=True,
    hide_index=False,
)

# Optional: choose save mode
mode = st.radio(
    "Save mode",
    ["Overwrite entire tab", "Append only new rows"],
    horizontal=True,
)

# ---- Save button ----
col1, col2 = st.columns([1,1])
with col1:
    if st.button("💾 Save changes to Google Sheets", type="primary"):
        try:
            if mode == "Overwrite entire tab":
                save_sheet(SHEET_ID, TAB_NAME, edited)
                st.success("Saved! The worksheet was fully overwritten.")
                st.toast("Google Sheet updated.", icon="✅")
                st.cache_data.clear()   # so next load gets fresh data
            else:
                # Append-only: find new rows vs original df by simple anti-join
                # (works best if you have a stable key column like 'Ticker')
                base = df.copy().fillna("").astype(str)
                neww = edited.copy().fillna("").astype(str)

                # If you have a known key column, set it here for stronger diff:
                key_col = None  # e.g., "Ticker"
                if key_col and key_col in neww.columns:
                    base = base.set_index(key_col, drop=False)
                    neww = neww.set_index(key_col, drop=False)
                    delta = neww.loc[~neww.index.isin(base.index)]
                else:
                    # Fallback: row-wise comparison
                    delta = pd.concat([neww, base]).drop_duplicates(keep=False)

                if delta.empty:
                    st.info("No new rows to append.")
                else:
                    gc = gspread.authorize(CREDS)
                    ws = gc.open_by_key(SHEET_ID).worksheet(TAB_NAME)
                    ws.append_rows(delta.values.tolist(), value_input_option="USER_ENTERED")
                    st.success(f"Appended {len(delta)} new row(s).")
                    st.toast("New rows appended.", icon="🧩")
                    st.cache_data.clear()
        except Exception as e:
            st.error(f"Save failed: {e}")

with col2:
    if st.button("🔄 Reload from Google Sheets"):
        st.cache_data.clear()
        st.rerun()
