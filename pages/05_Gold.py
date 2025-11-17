import streamlit as st
import requests
import pandas as pd 
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt


#----------------------------#
    # DECLARING FUNCTIONS #
#----------------------------#

@st.cache_data(ttl=15)
def fetch_live_gold():
    Live_Gold_Url = 'https://financialmodelingprep.com/stable/quote?symbol=XAUUSD&apikey=beUiETWAQ7Ert13VnAd7qkiEqjT1GrFC'
    Gold_Price = requests.get(Live_Gold_Url)
    return Gold_Price.json()

@st.cache_data(ttl=10000)
def fetch_histo_quotes():
    Historical_quotes_url = 'https://financialmodelingprep.com/stable/historical-price-eod/full?symbol=XAUUSD&from=2010-11-17&to=2025-11-17&apikey=beUiETWAQ7Ert13VnAd7qkiEqjT1GrFC'
    All_quotes = requests.get(Historical_quotes_url)
    return All_quotes.json()

def divider():
    st.markdown(
        "<hr style='border: 0; border-top: 1px solid #ddd; margin: 20px 0;'>",
        unsafe_allow_html=True
    )
#----------------------------#
    # EXECUTING FUNCTIONS #
#----------------------------#

Gold_info = fetch_live_gold()
Gold_Price = Gold_info[0]["price"]
P_Change = Gold_info[0]["changePercentage"]
P_Change_percent = f"{P_Change :.2f}%"

timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


#----------------------------#
    # TABLES #
#----------------------------#

Gold_History_Table = pd.DataFrame(fetch_histo_quotes())

Gold_History_Table["date"] = pd.to_datetime(Gold_History_Table["date"])
Gold_History_Table = Gold_History_Table.sort_values("date").set_index("date")

# Rename close → price for convenience
Gold_History_Table = Gold_History_Table.rename(columns={"close": "price"})

# Ensure numeric
numeric_cols = ["open", "high", "low", "price", "volume", "change", "changePercent", "vwap"]
for col in numeric_cols:
        if col in Gold_History_Table.columns:
            Gold_History_Table[col] = pd.to_numeric(Gold_History_Table[col], errors="coerce")

Gold_History_Table = Gold_History_Table.dropna(subset=["price"])
Gold_History_Table = Gold_History_Table[~Gold_History_Table.index.duplicated(keep="last")]


trading_days = 252

# Returns: from price
Gold_History_Table["ret"] = Gold_History_Table["price"].pct_change()

# API-provided changePercent (your sample shows it as decimal, e.g. -0.02488 ≈ -2.49%)
if "changePercent" in Gold_History_Table.columns:
    Gold_History_Table["ret_api"] = Gold_History_Table["changePercent"]
else:
    Gold_History_Table["ret_api"] = np.nan

Gold_History_Table["log_ret"] = np.log(Gold_History_Table["price"]).diff()

# Cumulative performance
Gold_History_Table["cum_growth"] = (1 + Gold_History_Table["ret"].fillna(0)).cumprod()
Gold_History_Table["cum_index"] = 100 * Gold_History_Table["cum_growth"] / Gold_History_Table["cum_growth"].iloc[0]

# Drawdown
Gold_History_Table["running_max"] = Gold_History_Table["cum_index"].cummax()
Gold_History_Table["drawdown"] = Gold_History_Table["cum_index"] / Gold_History_Table["running_max"] - 1

# Rolling volatility
Gold_History_Table["vol_30d"] = Gold_History_Table["ret"].rolling(30).std() * np.sqrt(trading_days)
Gold_History_Table["vol_90d"] = Gold_History_Table["ret"].rolling(90).std() * np.sqrt(trading_days)

# Monthly & DOW helpers
Gold_History_Table["year"] = Gold_History_Table.index.year
Gold_History_Table["month"] = Gold_History_Table.index.month
Gold_History_Table["dow"] = Gold_History_Table.index.day_name()

#----------------------------#
    # UI #
#----------------------------#

st.markdown(
    f"""
    <style>
    @keyframes pulse {{
        0%   {{ transform: scale(1);   }}
        50%  {{ transform: scale(1.02); }}
        100% {{ transform: scale(1);   }}
    }}
    .gold-pulse {{
        background: linear-gradient(135deg, #8d6e37, #d4af37, #f5d76e);
        padding: 20px;
        border-radius: 14px;
        text-align: center;
        color: white;
        font-size: 34px;
        font-weight: 700;
        letter-spacing: 1px;
        border: 1px solid rgba(255,255,255,0.25);
        backdrop-filter: blur(6px);
        animation: pulse 3s ease-in-out infinite;
        transform-origin: center;
    }}
    </style>

    <div class="gold-pulse">
        GOLD — ${Gold_Price:,.2f} ({P_Change_percent})
        <div style="
            font-size: 14px;
            font-weight: 400;
            margin-top: 6px;
            opacity: 0.9;
        ">
            <span style ="
            color: black;
            ">
            Updated: {timestamp}
            </span>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

divider()

st.dataframe(Gold_History_Table, hide_index=True)