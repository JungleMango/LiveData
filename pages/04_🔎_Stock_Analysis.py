import streamlit as st
import requests
import pandas as pd 

api_key = 'beUiETWAQ7Ert13VnAd7qkiEqjT1GrFC'
base_url = 'https://financialmodelingprep.com'
data_type = 'income-statement'
ticker = 'AAPL'
url = f'{base_url}/stable/{data_type}?symbol={ticker}&apikey={api_key}'

response = requests.get(url)
data = response.json()

df = pd.DataFrame(data).T

df