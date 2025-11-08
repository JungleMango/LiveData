import streamlit as st
import pandas as pd

First_Table = pd.DataFrame(
    [
        {"Ticker": "NVDA", "price": 4, "is_widget": True},
        {"Ticker": "TSLA", "price": 5, "is_widget": False},
        {"Ticker": "QQQ", "price": 3, "is_widget": True},
    ]
)

st.dataframe(First_Table, use_container_width=True)