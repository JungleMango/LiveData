import streamlit as st
import pandas as pd
import gspread
from google.oauth2 import service_account

# Build creds from secrets
creds = service_account.Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ],
)

SHEET_ID = st.secrets["sheets"]["sheet_id"]

@st.cache_data(ttl=60)
def read_sheet(sheet_id: str, tab: str):
    gc = gspread.authorize(creds)
    ws = gc.open_by_key(sheet_id).worksheet(tab)
    rows = ws.get_all_records()   # list[dict]
    return pd.DataFrame(rows)

df = read_sheet(SHEET_ID, "Portfolio")  # change to your tab name
st.dataframe(df, use_container_width=True)
