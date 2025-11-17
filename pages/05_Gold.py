import streamlit as st
import requests
import pandas as pd 



#----------------------------#
    # DECLARING FUNCTIONS #
#----------------------------#

@st.cache_data(ttl=15)
def fetch_live_gold():
    Live_Gold_Url = 'https://financialmodelingprep.com/stable/quote?symbol=XAUUSD&apikey=beUiETWAQ7Ert13VnAd7qkiEqjT1GrFC'
    Gold_Price = requests.get(Live_Gold_Url)
    return Gold_Price.json()

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
        <span style="
            padding: 18px;
            border-radius: 12px;
            text-align: center;
            color: white;
            font-size: 14px;
            font-weight: 700;
            box-shadow: 0 4px 12px rgba(0,0,0,0.25);
            letter-spacing: 1px;
        ">
            "Gold price — ${Gold_Price:,.2f}
        </span>
        """,
        unsafe_allow_html=True
    )
