import streamlit as st
from st_gsheets_connection import GSheetsConnection  # recommended package

conn = st.connection("gsheets", type=GSheetsConnection)

df = conn.read(
    spreadsheet="https://docs.google.com/spreadsheets/d/1CKDZqZIZ6WTbHGRuTf47DUxtlsSrBC5buZ6u8soQ-rw/edit",  # or just "YOUR_SHEET_ID"
    worksheet="Watchlist",
    ttl="10m",
    usecols=[0, 1],
    nrows=3,
)

st.write(df)