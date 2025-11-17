import streamlit as st
import requests
import pandas as pd 
from datetime import datetime

#----------------------------#
    # DECLARING FUNCTIONS #
#----------------------------#

@st.cache_data(ttl=15)
def fetch_live_gold():
    Live_Gold_Url = 'https://financialmodelingprep.com/stable/quote?symbol=XAUUSD&apikey=beUiETWAQ7Ert13VnAd7qkiEqjT1GrFC'
    Gold_Price = requests.get(Live_Gold_Url)
    return Gold_Price.json()

timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

#----------------------------#
    # EXECUTING FUNCTIONS #
#----------------------------#

Gold_info = fetch_live_gold()
Gold_Price = Gold_info[0]["price"]

#----------------------------#
    # UI #
#----------------------------#

st.write(f"Live Price — ${Gold_Price:,.2f}")
st.markdown(
    f"""
    <div style="
        background: linear-gradient(135deg, #8d6e37, #d4af37, #f5d76e);
        padding: 20px;
        border-radius: 14px;
        text-align: center;
        color: white;
        font-size: 34px;
        font-weight: 700;
        box-shadow: 0 8px 20px rgba(0,0,0,0.25);
        letter-spacing: 1px;
        border: 1px solid rgba(255,255,255,0.25);
        backdrop-filter: blur(6px);
    ">
        GOLD — ${Gold_Price:,.2f}
        <div style="
            font-size: 14px;
            font-weight: 400;
            margin-top: 6px;
            opacity: 0.9;
        ">
            Updated: {timestamp}
        </div>
    </div>
    """,
    unsafe_allow_html=True
)