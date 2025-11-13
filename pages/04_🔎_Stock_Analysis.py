import streamlit as st
import requests
import pandas as pd 

api_key = 'beUiETWAQ7Ert13VnAd7qkiEqjT1GrFC'
base_url = 'https://financialmodelingprep.com'
data_type = 'income-statement'
ticker = st.text_input("Enter Ticker")

Inc_Stat_Url = f'{base_url}/stable/{data_type}?symbol={ticker}&apikey={api_key}'
Quote_Url = f'{base_url}/stable/quote?symbol={ticker}&apikey=beUiETWAQ7Ert13VnAd7qkiEqjT1GrFC'


Live_Quote = requests.get(Quote_Url)
Income_Statement = requests.get(Inc_Stat_Url)


Quote_Price = Live_Quote.json()

Income_Statement_Table = Income_Statement.json()



QP = pd.DataFrame(Quote_Price)
IST = pd.DataFrame(Income_Statement_Table).T


## UI ##
st.subheader("Live Quote")
st.table(QP)
st.subheader("Income statement of the company")
st.table(IST, border=("horizontal"))