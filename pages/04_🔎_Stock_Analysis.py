import streamlit as st
import requests
import pandas as pd 

api_key = 'beUiETWAQ7Ert13VnAd7qkiEqjT1GrFC'
base_url = 'https://financialmodelingprep.com'
data_type = 'income-statement'
ticker = st.text_input("Enter Ticker")
years = '30'
time = 'quarter'

#----------------------------#
    # DECLARING FUNCTIONS #
#----------------------------#

# Creating a function to witch im giving a variable to it. 
# Function will return the data from specified website.
@st.cache_data(ttl=86400)
def fetch_income(ticker):
    Inc_Stat_Url = f'{base_url}/stable/{data_type}?symbol={ticker}&limit={years}&period={time}&apikey={api_key}' # variable to created url
    Income = requests.get(Inc_Stat_Url) # assigning variable to data requested from website
    return Income.json() # saving result as json


#----------------------------#
    # EXECUTING FUNCTIONS #
#----------------------------#
IST = pd.DataFrame(fetch_income(ticker))

#----------------------------#
    # UI / STYLING #
#----------------------------#

st.subheader("Income statement")
st.dataframe(IST, hide_index=True)
EPS = IST[["date","eps"]]

st.markdown("EPS per quarter")
st.dataframe(EPS, hide_index=True)