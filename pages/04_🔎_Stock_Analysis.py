import streamlit as st
import requests
import pandas as pd 

api_key = 'beUiETWAQ7Ert13VnAd7qkiEqjT1GrFC'
base_url = 'https://financialmodelingprep.com'
data_type = 'income-statement'
ticker = st.text_input("Enter Ticker")


# Quote_Url = f'{base_url}/stable/quote?symbol={ticker}&apikey=beUiETWAQ7Ert13VnAd7qkiEqjT1GrFC'

@st.cache_data(ttl=86400)
def fetch_income(ticker):
    Inc_Stat_Url = f'{base_url}/stable/{data_type}?symbol={ticker}&apikey={api_key}'
    Income = requests.get(Inc_Stat_Url)
    return Income.json()





IST = pd.DataFrame(fetch_income(ticker)).T




## UI ##
st.subheader("Income statement of the company")
st.table(IST, border=("horizontal"))