import streamlit as st
import requests
import pandas as pd 

api_key = 'beUiETWAQ7Ert13VnAd7qkiEqjT1GrFC'
base_url = 'https://financialmodelingprep.com'
data_type = 'income-statement'
ticker = st.text_input("Enter Ticker")
N = '30'

#----------------------------#
    # DECLARING FUNCTIONS 
#----------------------------#

# Creating a function to witch im giving a variable to it. 
# Function will return the data from specified website.
@st.cache_data(ttl=86400)
def fetch_income(ticker):
    Inc_Stat_Url = f'{base_url}/api/v3/{data_type}/{ticker}?limit={N}&apikey={api_key}' # variable to created url
    Income = requests.get(Inc_Stat_Url) # assigning variable to data requested from website
    return Income.json() # saving result as json



# {base_url}/stable/{data_type}?symbol={ticker}&apikey={api_key}

#----------------------------#
    # EXECUTING FUNCTIONS 
#----------------------------#

IST = pd.DataFrame(fetch_income(ticker))

#----------------------------#
    # UI / STYLING 
#----------------------------#

st.subheader("Income statement")
st.dataframe(IST)
EPS = IST['eps']
EPS