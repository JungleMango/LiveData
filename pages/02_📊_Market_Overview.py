# 02_📊_NVIDIA_Revenue.py
import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="NVIDIA Revenue Dashboard", layout="wide")

st.title("🟩 NVIDIA Revenue Dashboard")
st.caption("Q2 FY2026 snapshot with geographic mix, guidance, and China/export context.")

# ---------- Data (edit here if you need) ----------
# Streams: your numbers
streams = pd.DataFrame([
    {"Stream": "Compute & Networking", "Share": 89},
    {"Stream": "Graphics",             "Share": 11},
])

# Regions: your numbers
regions = pd.DataFrame([
    {"Region": "United States",   "Share": 46},
    {"Region": "Singapore",       "Share": 18},
    {"Region": "Taiwan",          "Share": 15},
    {"Region": "China",           "Share": 13},
    {"Region": "Other (incl. EU)","Share": 6},
])

# Optional comparison toggle (dummy Q1 vs Q2 for charts)
qoq = st.toggle("Show QoQ comparison (Q1 vs Q2 FY2026)", value=False)

if qoq:
    # Example QoQ figures (adjust if you have exacts)
    streams_qoq = pd.DataFrame([
        {"Quarter": "Q1 FY26", "Stream": "Compute & Networking", "Share": 88},
        {"Quarter": "Q1 FY26", "Stream": "Graphics",             "Share": 12},
        {"Quarter": "Q2 FY26", "Stream": "Compute & Networking", "Share": 89},
        {"Quarter": "Q2 FY26", "Stream": "Graphics",             "Share": 11},
    ])
    regions_qoq = pd.DataFrame([
        {"Quarter": "Q1 FY26", "Region": "United States",    "Share": 45},
        {"Quarter": "Q1 FY26", "Region": "Singapore",        "Share": 18},
        {"Quarter": "Q1 FY26", "Region": "Taiwan",           "Share": 15},
        {"Quarter": "Q1 FY26", "Region": "China",            "Share": 14},
        {"Quarter": "Q1 FY26", "Region": "Other (incl. EU)", "Share": 8},
        {"Quarter": "Q2 FY26", "Region": "United States",    "Share": 46},
        {"Quarter": "Q2 FY26", "Region": "Singapore",        "Share": 18},
        {"Quarter": "Q2 FY26", "Region": "Taiwan",           "Share": 15},
        {"Quarter": "Q2 FY26", "Region": "China",            "Share": 13},
        {"Quarter": "Q2 FY26", "Region": "Other (incl. EU)", "Share": 6},
    ])

# ---------- Layout ----------
col1, col2 = st.columns(2, gap="large")

with col1:
    st.subheader("Revenue Streams (Q2 FY2026)")
    if qoq:
        fig_streams = px.bar(
            streams_qoq, x="Stream", y="Share", color="Quarter", barmode="group",
            text="Share", labels={"Share": "% of Revenue"}, height=380
        )
    else:
        fig_streams = px.pie(
            streams, names="Stream", values="Share", hole=0.35,
            height=380
        )
        fig_streams.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(fig_streams, use_container_width=True)
    st.markdown(
        "Compute & Networking is the **core driver (~89%)**: Data Center, Automotive, Jetson, and DGX Cloud. "
        "Graphics is **~11%**, buoyed by GeForce/RTX and Omniverse."
    )

with col2:
    st.subheader("Revenue by Country")
    if qoq:
        fig_regions = px.bar(
            regions_qoq, x="Region", y="Share", color="Quarter", barmode="group",
            text="Share", labels={"Share": "% of Revenue"}, height=380
        )
    else:
        fig_regions = px.bar(
            regions, x="Region", y="Share", text="Share",
            labels={"Share": "% of Revenue"}, height=380
        )
    fig_regions.update_layout(xaxis_tickangle=-20)
    st.plotly_chart(fig_regions, use_container_width=True)
    st.markdown(
        "🇺🇸 **US ~46%** | 🇸🇬 Singapore **18%** | 🇹🇼 Taiwan **15%** | 🇨🇳 China **13%** | 🌍 Other (incl. EU) **6%**"
    )

# ---------- Narrative / Guidance ----------
st.divider()
st.subheader("Guidance & Regional Developments")
st.markdown(
    "- **Guidance:** Next-quarter revenue **~$54.0B ±2%**. Outlook assumes **no H20 shipments to China**.\n"
    "- **Europe:** Partnering with **France, Germany, Italy, Spain, and the U.K.** on **Blackwell AI infrastructure** "
    "including the *first industrial AI cloud for European manufacturers* — despite Europe currently contributing **<6%**."
)

st.subheader("Geopolitics & Export Controls")
st.markdown(
    "> “China is nanoseconds behind America in AI. It’s vital that America wins by racing ahead and winning developers worldwide.” — **Jensen Huang**\n\n"
    "- NVIDIA has indicated China restrictions are **“deeply painful,”** estimating up to **$15B** potential annual sales impact.\n"
    "- China is still material (≈ **$17B**, FY2025 est.) and remains a key risk factor alongside **Middle East** export limits "
    "(e.g., constrained GB300 shipments to the UAE despite limited licenses)."
)

st.caption(
    "Tip: To control how this page appears in the sidebar, use a filename like "
    "`02_📊_NVIDIA_Revenue.py` in the `pages/` folder. The emoji/text become the sidebar label."
)
