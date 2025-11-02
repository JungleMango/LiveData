import streamlit as st
import yfinance as yf

st.title("Live QQQ Price")
price = yf.Ticker("QQQ").history(period="1d")["Close"].iloc[-1]
st.metric("QQQ Price", f"${price:.2f}")
