import streamlit as st
from utilities.ocr_gptvision import ocr_gpt
import os

def home_page():
    # --- HEADER SECTION ---
    st.markdown(
        """
        <div style="text-align: center; margin-bottom: 40px;">
            <h1 style="font-size: 3rem; color: #202124; margin-bottom: 0;">Project Raseed</h1>
            <p style="font-size: 1.2rem; color: #5f6368;">
                Google Cloud Agentic AI Demo • Powered by <span style="color: #1A73E8; font-weight: 600;">Gemini 1.5 Pro</span>
            </p>
        </div>
        """,
        unsafe_allow_html=True
    )

    # --- MAIN UPLOAD CARD ---
    # We use columns to center the card on the screen
    col_left, col_center, col_right = st.columns([1, 2, 1])

    with col_center:
        st.markdown(
            """
            <div style="background-color: white; padding: 20px; border-radius: 12px; border: 1px solid #dadce0; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                <h3 style="text-align: center; color: #202124; margin-top: 0;">📄 Quick Scan</h3>
                <p style="text-align: center; color: #5f6368; font-size: 0.9rem;">Upload a receipt to extract data instantly</p>
            </div>
            """, 
            unsafe_allow_html=True
        )
        
        # The Form is visually inside the card logic
        with st.form("upload_form", clear_on_submit=True, border=False):
            uploaded_file = st.file_uploader("", type=["jpg", "png", "jpeg", "pdf"], label_visibility="collapsed")
            
            # Center the button using columns inside the form
            c1, c2, c3 = st.columns([1, 2, 1])
            with c2:
                submitted = st.form_submit_button("Run Analysis", type="primary", use_container_width=True)

            if submitted and uploaded_file:
                user_email = st.session_state['user_info'].get('email')
                file_path = os.path.join("uploaded_invoices", user_email, uploaded_file.name)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                with st.spinner("Gemini is processing..."):
                    ocr_gpt(file_path)
                
                st.balloons()
                st.success("Receipt Digitized! Check 'Raseed Database'.")

    st.markdown("---")

    # --- GOOGLE-STYLE FEATURE GRID ---
    # Using the official Google colors for the headers
    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown("### <span style='color:#EA4335'>01.</span> Ingest", unsafe_allow_html=True)
        st.markdown("**Gemini Vision** instantly extracts merchant details, line items, and taxes from any image.")

    with c2:
        st.markdown("### <span style='color:#FBBC04'>02.</span> Process", unsafe_allow_html=True)
        st.markdown("Data is structured into **Firestore** and analyzed for spending habits and inventory.")

    with c3:
        st.markdown("### <span style='color:#34A853'>03.</span> Action", unsafe_allow_html=True)
        st.markdown("Get a dynamic **Google Wallet Pass** and ask the Agent questions about your money.")