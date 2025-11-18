import streamlit as st
import requests
import pandas as pd 
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick



api_key = 'beUiETWAQ7Ert13VnAd7qkiEqjT1GrFC'
base_url = 'https://financialmodelingprep.com'
data_type = 'income-statement'
ticker = st.text_input("Enter Ticker")
st.write = ("Data pulled from Nov 17 2010")
years = '120'
time = 'quarter'

#----------------------------#
    # DECLARING FUNCTIONS #
#----------------------------#

@st.cache_data(ttl=10000)
def fetch_histo_quotes(ticker):
    Historical_quotes_url = f'{base_url}/stable/historical-price-eod/full?symbol={ticker}&from=2010-11-17&to=2025-11-17&apikey={api_key}'
    All_quotes = requests.get(Historical_quotes_url)
    return All_quotes.json()

#----------------------------#
    # EXECUTING FUNCTIONS #
#----------------------------#

All_Quotes = fetch_histo_quotes(ticker)
Ticker_Price_log = pd.DataFrame(All_Quotes)

Ticker_Price_log