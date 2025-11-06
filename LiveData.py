# 00_🏠_Home.py
import time
from datetime import datetime, timezone

import streamlit as st

# ---------- Page config ----------. L?.
st.set_page_config(
    page_title="Live Data — Home",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- Sidebar (custom links) ----------
with st.sidebar:
    st.markdown("## 🧭 Navigation")
    # If your pages are named like "01_📊_Market_Overview.py" etc.,
    # you can add pretty labels with page_link:
    try:
        st.page_link("pages/01_📊_Market_Overview.py", label="📊 Market Overview")
        st.page_link("pages/02_⚙️_Watchlist.py", label="⚙️ Watchlist")
        st.page_link("pages/03_📈_Bell_Curve.py", label="📈 Bell Curve")
        st.page_link("pages/04_🧪_Playground.py", label="🧪 Playground")
    except Exception:
        # Older Streamlit versions may not have page_link—ignore gracefully
        pass

    st.divider()
    auto_refresh = st.toggle("Auto-refresh", value=False, help="Refresh the home widgets every few seconds")
    interval = st.number_input("Refresh every (sec)", min_value=5, max_value=120, value=30, step=5)

# ---------- Header ----------
st.title("🏠 Live Data Dashboard — Home")
st.caption("Either you make it or loose it all, choice is yours, luck is not")

# ---------- Status/KPI row (placeholders you can wire up) ----------
kpi1, kpi2, kpi3, kpi4 = st.columns(4)

def render_kpis():
    # Replace these with real values from your cache/API
    kpi1.metric("Active Portfolios", 2)
    kpi2.metric("Tracked Tickers", 14, help="Unique symbols across all portfolios")
    kpi3.metric("Server Status", "✅ Online")
    kpi4.metric("Last Update (UTC)", datetime.now(timezone.utc).strftime("%H:%M:%S"))

# ---------- Main content ----------
placeholder = st.empty()

def render_body():
    with placeholder.container():
        render_kpis()
        st.divider()

        left, right = st.columns([2, 1])

        with left:
            st.subheader("Overview")
            st.write(
                "Welcome! Use the sidebar to jump to other pages. "
                "This home screen is kept intentionally simple: a few KPIs, an activity feed, "
                "and quick links. Wire these widgets to your actual API/cache."
            )

            with st.expander("How to connect your live data", expanded=False):
                st.markdown(
                    """
                    1. Fetch or cache quotes in a background thread or API layer.  
                    2. Store latest values in `st.session_state` or your own cache.  
                    3. Replace the KPI placeholders with real numbers.  
                    4. (Optional) Use `st.cache_data` / `st.cache_resource` for efficient reuse.
                    """
                )

        with right:
            st.subheader("Quick Links")
            st.link_button("Go to Market Overview", "#", use_container_width=True)
            st.link_button("Open Watchlist", "#", use_container_width=True)
            st.link_button("Bell Curve Tool", "#", use_container_width=True)

        st.divider()
        st.subheader("Recent Activity")
        st.write(
            "- Loaded portfolios: **Long-Term (USD)**, **TFSA (CAD)**\n"
            "- Refreshed quotes: `QQQ`, `NVDA`, `TSLA`, `AAPL`…\n"
            "- Cache TTL: **30s** | Rate limit: **60s/ticker**"
        )

# First paint
render_body()

# Optional auto-refresh loop (only runs while you're on this page)
if auto_refresh:
    # NOTE: Streamlit reruns the script; we emulate a simple loop using st.experimental_rerun
    # by sleeping and letting Streamlit rerun on each refresh tick via "empty" container
    # This keeps the page snappy without manual while True loops.
    # Sleep then prompt a rerun:
    time.sleep(interval)
    st.experimental_rerun()
