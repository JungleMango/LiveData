import streamlit as st
import requests
import pandas as pd

# =========================
#        CONFIG
# =========================
st.set_page_config(
    page_title="Stock Snapshot – FMP",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Small CSS polish (card feel, nicer tables) ---
st.markdown(
    """
    <style>
    /* Center the main content a bit and give it breathing room */
    .main > div {
        padding-top: 1rem;
        padding-left: 1.5rem;
        padding-right: 1.5rem;
    }

    /* Make metric cards stand out slightly */
    .stMetric {
        background: rgba(240, 246, 255, 0.7);
        padding: 0.75rem 0.75rem;
        border-radius: 0.75rem;
        border: 1px solid rgba(180, 200, 230, 0.7);
    }

    /* Optional: soften table edges */
    [data-testid="stTable"] table {
        border-radius: 0.5rem;
        overflow: hidden;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================
#      API CONSTANTS
# =========================
api_key = "beUiETWAQ7Ert13VnAd7qkiEqjT1GrFC"
base_url = "https://financialmodelingprep.com"
data_type = "income-statement"


# =========================
#      HELPERS
# =========================
@st.cache_data(ttl=86400)
def fetch_income(ticker: str):
    url = f"{base_url}/stable/{data_type}?symbol={ticker}&apikey={api_key}"
    r = requests.get(url)
    r.raise_for_status()
    return r.json()


@st.cache_data(ttl=300)
def fetch_quote(ticker: str):
    url = f"{base_url}/stable/quote?symbol={ticker}&apikey={api_key}"
    r = requests.get(url)
    r.raise_for_status()
    return r.json()


def fmt_big_number(x):
    """Format large numbers as K / M / B / T."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return x
    abs_x = abs(x)
    if abs_x >= 1_000_000_000_000:
        return f"{x/1_000_000_000_000:.2f}T"
    if abs_x >= 1_000_000_000:
        return f"{x/1_000_000_000:.2f}B"
    if abs_x >= 1_000_000:
        return f"{x/1_000_000:.2f}M"
    if abs_x >= 1_000:
        return f"{x/1_000:.2f}K"
    return f"{x:.2f}"


# =========================
#          UI
# =========================

st.title("📊 Stock Snapshot")
st.caption("Live quote + income statement via FinancialModelingPrep")

with st.sidebar:
    st.header("⚙️ Settings")
    ticker = st.text_input("Ticker symbol", value="AAPL").upper().strip()
    st.write("Enter any valid symbol (e.g., AAPL, MSFT, NVDA).")

if not ticker:
    st.info("👈 Enter a ticker in the sidebar to begin.")
    st.stop()

# --- Fetch data ---
try:
    with st.spinner(f"Fetching data for **{ticker}**..."):
        quote_raw = fetch_quote(ticker)
        income_raw = fetch_income(ticker)
except requests.HTTPError as e:
    st.error(f"API error: {e}")
    st.stop()
except Exception as e:
    st.error(f"Something went wrong: {e}")
    st.stop()

# --- Guard: no data cases ---
if not quote_raw or isinstance(quote_raw, dict) and quote_raw.get("Error Message"):
    st.error(f"No quote data returned for symbol: {ticker}")
    st.stop()

if not income_raw or isinstance(income_raw, dict) and income_raw.get("Error Message"):
    st.warning(f"No income statement data returned for symbol: {ticker}")
    income_raw = []

# =========================
#     QUOTE SECTION
# =========================

# FMP quote is usually a list with one dict
q = quote_raw[0] if isinstance(quote_raw, list) and len(quote_raw) > 0 else quote_raw

price = q.get("price")
change = q.get("change")
change_pct = q.get("changesPercentage")
market_cap = q.get("marketCap")
pe = q.get("pe")
eps = q.get("eps")
volume = q.get("volume")
avg_volume = q.get("avgVolume")

st.subheader(f"💵 Live Quote – {ticker}")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="Price",
        value=f"${price:.2f}" if isinstance(price, (int, float)) else price,
        delta=f"{change:+.2f}" if isinstance(change, (int, float)) else None,
    )

with col2:
    pct_str = f"{change_pct:.2f}%" if isinstance(change_pct, (int, float)) else str(
        change_pct
    )
    st.metric(
        label="Daily Change %",
        value=pct_str,
    )

with col3:
    st.metric(
        label="Market Cap",
        value=fmt_big_number(market_cap),
    )

with col4:
    pe_str = f"{pe:.2f}" if isinstance(pe, (int, float)) else pe
    st.metric("P/E Ratio", pe_str)

# Extra stats row
st.markdown("### 📌 Additional Quote Details")
c1, c2 = st.columns(2)

with c1:
    extra_left = {
        "EPS": eps,
        "Volume": fmt_big_number(volume),
        "Avg Volume": fmt_big_number(avg_volume),
    }
    st.table(
        pd.DataFrame.from_dict(extra_left, orient="index", columns=["Value"])
    )

with c2:
    extra_right = {
        "Open": q.get("open"),
        "Previous Close": q.get("previousClose"),
        "Year High": q.get("yearHigh"),
        "Year Low": q.get("yearLow"),
    }
    st.table(
        pd.DataFrame.from_dict(extra_right, orient="index", columns=["Value"])
    )

# =========================
#   INCOME STATEMENT
# =========================

st.markdown("---")
st.subheader(f"📘 Income Statement – {ticker}")

if not income_raw:
    st.info("No income statement data available.")
else:
    ist_df = pd.DataFrame(income_raw)

    # Try to order by date (newest first)
    if "date" in ist_df.columns:
        ist_df["date"] = pd.to_datetime(ist_df["date"], errors="coerce")
        ist_df = ist_df.sort_values("date", ascending=False)

    # Let user select how many periods to show
    max_periods = min(10, len(ist_df))
    periods_to_show = st.slider(
        "Number of periods to display",
        min_value=1,
        max_value=max_periods,
        value=max_periods,
        step=1,
    )

    ist_show = ist_df.head(periods_to_show).copy()

    # Make numeric columns pretty
    num_cols = ist_show.select_dtypes(include="number").columns
    ist_show[num_cols] = ist_show[num_cols].applymap(fmt_big_number)

    # Put date / period columns first if they exist
    preferred_order = [c for c in ["date", "calendarYear", "period"] if c in ist_show.columns]
    other_cols = [c for c in ist_show.columns if c not in preferred_order]
    ist_show = ist_show[preferred_order + other_cols]

    st.dataframe(
        ist_show,
        use_container_width=True,
        height=400,
    )
