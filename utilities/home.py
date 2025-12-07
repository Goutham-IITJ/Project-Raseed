import streamlit as st
from utilities.ocr_gptvision import ocr_gpt  # We need this back!
from utilities.authentication import google_auth
from PIL import Image
import io
import os

def home_page():
    # --- HEADER ---
    st.title("Project Raseed")
    st.caption("Google Cloud Agentic AI Demo")

    st.write("Transform financial chaos into structured insights with **Gemini 1.5 Pro**.")

    # --- ACTION AREA (QUICK UPLOAD) ---
    st.divider()
    col_upload, col_instruction = st.columns([1, 1], gap="large")

    with col_upload:
        st.subheader("⚡ Quick Scan")
        with st.form("upload_form", clear_on_submit=True, border=False):
            uploaded_file = st.file_uploader("Drop a receipt here", type=["jpg", "png", "jpeg"])
            submitted = st.form_submit_button("Analyze Receipt", type="primary")
            
            if submitted and uploaded_file:
                # Save locally for the "Local DB" patch
                user_email = st.session_state['user_info'].get('email')
                file_path = os.path.join("uploaded_invoices", user_email, uploaded_file.name)
                
                # Ensure directory exists
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                
                # Save file
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                # Run Gemini Vision
                with st.spinner("Gemini is reading your receipt..."):
                    ocr_gpt(file_path)
                
                st.success("Processed! Check 'Raseed Database' or Ask the Agent.")

    with col_instruction:
        st.info("💡 **Demo Tip:** Upload a receipt image to populate the database.")
        st.markdown("""
        **What happens next?**
        1. **Vision:** Gemini extracts merchant, items, and tax.
        2. **Storage:** Data is structured into SQL.
        3. **Agent:** You can ask questions like *"How much is the tax?"*
        """)

    st.divider()

    # --- FEATURE GRID (The Pitch) ---
    col1, col2, col3 = st.columns(3)
    with col1:
        st.write("📸 **Visual Ingestion**")
        st.caption("Gemini Vision Pro")
    with col2:
        st.write("🧠 **Agentic Reasoning**")
        st.caption("LangChain SQL Agent")
    with col3:
        st.write("💳 **Wallet Sync**")
        st.caption("Google Wallet API")

    # --- SAMPLE QUERIES ---
    st.divider()
    st.subheader("Try asking Raseed:")
    st.code("How much did I spend on groceries last month?", language="text")
    st.code("Show me a breakdown of my tax spending.", language="text")