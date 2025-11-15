import streamlit as st
import requests
import pandas as pd 

api_key = 'beUiETWAQ7Ert13VnAd7qkiEqjT1GrFC'
base_url = 'https://financialmodelingprep.com'
data_type = 'income-statement'
ticker = st.text_input("Enter Ticker")
years = '120'
time = 'quarter'

#----------------------------#
    # DECLARING FUNCTIONS #
#----------------------------#

# Creating a function to witch im giving a variable to it. 
# Function will return the data from specified website.
@st.cache_data(ttl=86400)
def fetch_income(ticker):
    Inc_Stat_Url = f'{base_url}/stable/{data_type}?symbol={ticker}&limit={years}&period={time}apikey={api_key}' # variable to created url
    Income = requests.get(Inc_Stat_Url) # assigning variable to data requested from website
    return Income.json() # saving result as json
# {base_url}/stable/{data_type}?symbol={ticker}&limit={years}&period={time}&apikey={api_key}
@st.cache_data(ttl=100)
def fetch_quote(ticker):
    Hquotes_url = f'{base_url}/stable/historical-price-eod/light?symbol={ticker}&from=2000-11-15&to=2025-11-15&apikey={api_key}'
    H_Quotes = requests.get(Hquotes_url)
    return H_Quotes.json()

#----------------------------#
    # EXECUTING FUNCTIONS #
#----------------------------#
Income_statement_table = pd.DataFrame(fetch_income(ticker))
Quote_table = pd.DataFrame(fetch_quote(ticker))
EPS_table = Income_statement_table[["date","eps"]]

EPS_table["date"] = pd.to_datetime(EPS_table["date"])
Quote_table["date"] = pd.to_datetime(Quote_table["date"])
EPS_table = EPS_table.sort_values("date")
Quote_table = Quote_table.sort_values("date")

analysis_table = pd.merge_asof(
    EPS_table,
    Quote_table,
    on="date"
      # match last price <= EPS date
)
analysis_table["PE Ratio"] = analysis_table["price"] / analysis_table["eps"]
analysis_table["Return Expectation"] = analysis_table["eps"] / analysis_table["PE Ratio"]


#----------------------------#
    # UI / STYLING #
#----------------------------#

st.markdown("Income statement")
st.dataframe(Income_statement_table, hide_index=True)


st.markdown("EPS per quarter")
st.dataframe(EPS_table, hide_index=True)

st.markdown("Histoical prices")
st.dataframe(Quote_table, hide_index=True)

st.subheader(" Analysis table: Yearly P/E")
analysis_table = analysis_table.drop(columns=["symbol"])
st.dataframe(analysis_table, hide_index=True)

