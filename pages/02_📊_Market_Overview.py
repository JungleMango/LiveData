import streamlit as st

# streamlit_app/pages/01_Markets.py
# ----------------------------------
# 👇 This comment controls how the page appears in the sidebar:
# Page title: Market Overview
# Page icon: 📊


st.set_page_config(page_title="Market Overview",
                   page_icon="📊",
                   layout="wide",
                   initial_sidebar_state="expanded")  # ensure nav is visible


st.title("🌍 Market Overview")
st.markdown("Here you can add charts, indices, or macro data.")

# Example content
st.line_chart({"S&P 500": [4000, 4200, 4150, 4300, 4400]})
