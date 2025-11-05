# app.py
import streamlit as st
from pages import markets, portfolio, currencies

PAGES = {
    "📊 Market Overview": markets,
    "💼 Portfolio Dashboard": portfolio,
    "💱 Currencies": currencies
}

st.sidebar.title("Navigation")
choice = st.sidebar.radio("Go to", list(PAGES.keys()))
page = PAGES[choice]
page.run()
