import streamlit as st
import yfinance as yf

st.title("💰 Live Bitcoin Price (BTC-USD)")

# Fetch Bitcoin price
data = yf.Ticker("BTC-USD").history(period="1d", interval="1m")

if not data.empty:
    price = data["Close"].iloc[-1]
    st.metric("BTC Price", f"${price:,.2f}")
    st.line_chart(data["Close"])
else:
    st.warning("No data available. Market might be closed or API rate-limited.")
