import streamlit as st

col1, col2 = st.columns([2,1], vertical_alignment='center', gap='large')

with col1:
    st.header("About Project Raseed")
    st.caption("Built for Google Cloud Agentic AI Day")

    st.write("""
        **Project Raseed** is a next-generation financial assistant designed to bridge the gap between 
        physical receipts and digital financial health.
        
        Unlike traditional expense trackers that rely on manual data entry, Raseed uses **Agentic AI** to autonomously parse, categorize, and reason about your spending habits.
        """)

    st.subheader("Technical Architecture")
    st.markdown("""
    * [cite_start]**Intelligence:** Google Gemini 1.5 Pro (Vision & Language) [cite: 112]
    * [cite_start]**Orchestration:** LangChain SQL Agent (Zero-Shot Reasoning) [cite: 113]
    * **Frontend:** Streamlit (Python)
    * [cite_start]**Database:** Local SQLite (Simulating Firebase Firestore) [cite: 115]
    """)

    st.subheader("The Problem")
    st.write("""
        Receipts are rich in data (SKUs, Taxes, Merchant Info) but are often treated as waste. 
        Raseed digitizes this "Dark Data" to enable features like **Inventory Tracking** and **Contextual Budgeting** directly inside Google Wallet.
    """)

with col2:
    # If you have a team logo, put it here. Otherwise, the app icon works.
    st.image("images/invoicegpt_icon.png", caption="Raseed Engine")

st.divider()

st.subheader("Developer")
st.markdown("**Name:** Goutham A.S")
st.markdown("**Focus:** Receipt Management for Google Wallet ")