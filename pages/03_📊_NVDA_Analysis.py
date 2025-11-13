import streamlit as st
import requests
import pandas as pd 

api_key = 'beUiETWAQ7Ert13VnAd7qkiEqjT1GrFC'
base_url = 'https://financialmodelingprep.com'
data_type = 'income-statement'

ticker = st.text_input("Enter Ticker")

@st.cache_data(ttl=86400)
def fetch_income(ticker: str):
    url = f"{base_url}/stable/{data_type}?symbol={ticker}&apikey={api_key}"
    r = requests.get(url)
    return r.json()

@st.cache_data(ttl=300)
def fetch_quote(ticker: str):
    url = f"{base_url}/stable/quote?symbol={ticker}&apikey={api_key}"
    r = requests.get(url)
    return r.json()

if ticker:
    # Get data
    income_data = fetch_income(ticker)
    quote_data = fetch_quote(ticker)

    # Convert to DataFrames
    IST = pd.DataFrame(income_data).T
    QP = pd.DataFrame(quote_data)

    # UI
    st.subheader("Live Quote")
    st.table(QP)

    st.subheader("Income Statement of the Company")
    st.table(IST)
else:
    st.write("👆 Enter a ticker above to load data.")
