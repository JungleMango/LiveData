import streamlit as st
import requests
import pandas as pd 
import matplotlib.pyplot as plt
from streamlit_autorefresh import st_autorefresh

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
    Inc_Stat_Url = f'{base_url}/stable/{data_type}?symbol={ticker}&limit={years}&period={time}&apikey={api_key}' # variable to created url
    Income = requests.get(Inc_Stat_Url) # assigning variable to data requested from website
    return Income.json() # saving result as json
# {base_url}/stable/{data_type}?symbol={ticker}&limit={years}&period={time}&apikey={api_key}
@st.cache_data(ttl=100)
def fetch_quote(ticker):
    Hquotes_url = f'{base_url}/stable/historical-price-eod/light?symbol={ticker}&from=2010-11-15&to=2025-11-15&apikey={api_key}'
    H_Quotes = requests.get(Hquotes_url)
    return H_Quotes.json()

@st.cache_data(ttl=15)
def fetch_live_quote(ticker):
    Live_Quote_Url = f'{base_url}/stable/quote?symbol={ticker}&apikey={api_key}'
    Live_Price = requests.get(Live_Quote_Url)
    return Live_Price.json()

def section_title(title):
    st.markdown(
        f"""
        <div style="
            margin-top: 30px;
            padding: 12px 16px;
            background-color: #2a915e;
            border-left: 4px solid #1b2129;
            border-radius: 4px;
            font-size: 20px;
            text-align: center;
            font-weight: 600;
        ">
            {title}
        </div>
        """,
        unsafe_allow_html=True
    )
def divider():
    st.markdown(
        "<hr style='border: 0; border-top: 1px solid #ddd; margin: 20px 0;'>",
        unsafe_allow_html=True
    )
def price_card(live_price, ticker):
    st.markdown(
        f"""
        <span style="
            padding: 18px;
            border-radius: 12px;
            text-align: center;
            color: white;
            font-size: 14px;
            font-weight: 700;
            box-shadow: 0 4px 12px rgba(0,0,0,0.25);
            letter-spacing: 1px;
        ">
            {ticker} — ${live_price:,.2f}
        </div>
        """,
        unsafe_allow_html=True
    )



#----------------------------#
    # EXECUTING FUNCTIONS #
#----------------------------#
Live_Price = fetch_live_quote(ticker)
st_autorefresh(interval=10000, key="refresh_Live_price")
Price = Live_Price[0]["price"]

Income_statement_table = pd.DataFrame(fetch_income(ticker))
Quote_table = pd.DataFrame(fetch_quote(ticker))
EPS_table = Income_statement_table[["date","eps","period"]]

EPS_table["Date"] = pd.to_datetime(EPS_table["date"])
Quote_table["Date"] = pd.to_datetime(Quote_table["date"])
EPS_table = EPS_table.sort_values("Date")
Quote_table = Quote_table.sort_values("Date")


# Merging Tables
analysis_table = pd.merge_asof(
    EPS_table,
    Quote_table,
    on="Date"
      # match last price <= EPS date
)
analysis_table["PE Ratio"] = analysis_table["price"] / analysis_table["eps"]
analysis_table["Return Expectation"] = analysis_table["eps"] / analysis_table["PE Ratio"]

# 1-year trailing return (compounded last 4 quarters)
analysis_table["TTM_Return"] = (
    (1 + analysis_table["Return Expectation"]).rolling(4).apply(lambda x: x.prod()) - 1
)


#----------------------------#
    # CHARTING #
#----------------------------#

plt.style.use("seaborn-v0_8-whitegrid")   # clean, modern, minimal

fig, ax = plt.subplots(figsize=(11, 5))

# Plot selected metrics
ax.plot(Income_statement_table["fiscalYear"], Income_statement_table["revenue"], 
        label="Revenue", linewidth=2.2, color="#1f77b4")

ax.plot(Income_statement_table["fiscalYear"], Income_statement_table["grossProfit"], 
        label="Gross Profit", linewidth=2.2, color="#2ca02c")

ax.plot(Income_statement_table["fiscalYear"], Income_statement_table["ebitda"], 
        label="EBITDA", linewidth=2.2, color="#ff7f0e")

# Clean formatting
ax.set_title("Income Statement Trends", fontsize=18, weight="bold", pad=15)
ax.set_xlabel("fiscalYear", fontsize=12)
ax.set_ylabel("Amount (USD)", fontsize=12)

ax.tick_params(axis="x", rotation=45)
ax.tick_params(axis="both", labelsize=11)

# Clean grid
ax.grid(alpha=0.25)

# Remove top & right borders
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

# Legend
ax.legend(frameon=False, fontsize=11)

st.pyplot(fig)

#----------------------------#
    # UI / STYLING #
#----------------------------#

st.write(f"Live Price — ${Price:,.2f}")


section_title("Income statement")
st.dataframe(Income_statement_table, hide_index=True)
divider()

section_title("EPS per quarter")
st.dataframe(EPS_table, hide_index=True)
divider()

section_title("Histoical prices")
st.dataframe(Quote_table, hide_index=True)
divider()

section_title(" Analysis table: Quarterly EPS and Return Expectations")
st.markdown(" P/E is the amount investors want to pay to get a return of eps (Expeted Return)")
analysis_table["TTM Annualized (%)"] = (analysis_table["TTM_Return"] * 100).round(2).astype(str) + "%"
analysis_table["Return Expectation (%)"] = (analysis_table["Return Expectation"] * 100).round(2).astype(str)+ "%"
analysis_table["EPS ($)"] = "$" + analysis_table["eps"].astype(str)
analysis_table["Price ($)"] = "$" + analysis_table["price"].astype(str)
analysis_table["Date_x"] = analysis_table["date_x"]
#analysis_table["PE Ratio ($)"] = "$" + analysis_table["PE Ratio"].astype(str)

analysis_table = (
    analysis_table
    .drop(columns=["symbol","date_y","Date","volume","TTM_Return"])
    [["Date_x","period","Price ($)","EPS ($)","PE Ratio","Return Expectation (%)","TTM Annualized (%)"]]
    .dropna()
    .sort_values("Date_x", ascending=False)
)

# Center everything
styled = (
    analysis_table.style
        .set_properties(**{'text-align': 'center'})
        .set_table_styles([dict(selector='th', props=[('text-align', 'center')])])
)

st.dataframe(styled, hide_index=True)


