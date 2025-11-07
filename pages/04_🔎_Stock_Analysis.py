import streamlit as st
import pandas as pd
import gspread
from google.oauth2 import service_account

st.set_page_config(page_title="Sheets (Private) → Streamlit")

# auth
creds = service_account.Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"]
)

@st.cache_data(ttl=60)
def pull_sheet(spreadsheet_name: str, worksheet_name: str) -> pd.DataFrame:
    gc = gspread.authorize(creds)
    sh = gc.open(spreadsheet_name).worksheet(worksheet_name)
    rows = sh.get_all_records()  # returns list[dict]
    return pd.DataFrame(rows)

df = pull_sheet("My Data Hub", "Watchlist")
st.dataframe(df, use_container_width=True)

# Optional: write back to Sheets
if st.button("Append timestamp"):
    gc = gspread.authorize(creds)
    ws = gc.open("My Data Hub").worksheet("Watchlist")
    ws.append_row(["Streamlit wrote this", st.session_state.get("ts")])
    st.success("Appended a row.")
