import streamlit as st


st.title("🌍 Market Overview")
st.markdown("Here you can add charts, indices, or macro data.")

# Example content
st.line_chart({"S&P 500": [4000, 4200, 4150, 4300, 4400]})
