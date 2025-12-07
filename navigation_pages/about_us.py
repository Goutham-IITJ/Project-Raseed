import streamlit as st

def about_us():
    # --- HERO SECTION ---
    st.markdown("""
    <div style="text-align: center; margin-bottom: 40px;">
        <h2 style="font-size: 2.5rem; color: #202124; margin-bottom: 10px;">Making every receipt speak.</h2>
        <p style="font-size: 1.2rem; color: #5f6368; max-width: 700px; margin: 0 auto;">
            Project Raseed transforms everyday receipts into dynamic Google Wallet passes and 
            real-time financial insights using Agentic AI.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # --- MAIN CONTENT GRID ---
    col1, col2 = st.columns([1.5, 1], gap="large")

    with col1:
        # --- CARD: THE VISION ---
        st.markdown("""
        <div style="background-color: white; padding: 24px; border-radius: 12px; border: 1px solid #dadce0; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 24px;">
            <h3 style="color: #1A73E8; margin-top: 0;">🚀 The Problem & Solution</h3>
            <p style="color: #3c4043; line-height: 1.6;">
                <b>The Problem:</b> Receipts are "Dark Data"—rich in SKUs, taxes, and merchant info, but often discarded or trapped in static photos.
                <br><br>
                <b>The Solution:</b> Raseed digitizes this data instantly. It doesn't just track expenses; it creates 
                <b>Interactive Wallet Passes</b> and enables you to "chat" with your purchase history (e.g., <i>"Do I have enough detergent?"</i>).
            </p>
        </div>
        """, unsafe_allow_html=True)

        # --- CARD: UNIQUE SELLING PROPOSITION ---
        st.markdown("""
        <div style="background-color: white; padding: 24px; border-radius: 12px; border: 1px solid #dadce0; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
            <h3 style="color: #34A853; margin-top: 0;">✨ Why Raseed?</h3>
            <ul style="color: #3c4043; line-height: 1.6; padding-left: 20px;">
                <li><b>Beyond Totals:</b> We digitize every single line item, not just the final price.</li>
                <li><b>Cumulative Memory:</b> Builds a searchable inventory of your household over time.</li>
                <li><b>Google Ecosystem:</b> Deep integration with Wallet, Gemini, and Cloud.</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        # --- CARD: TECH STACK ---
        st.markdown("""
        <div style="background-color: #F8F9FA; padding: 24px; border-radius: 12px; border: 1px solid #dadce0;">
            <h4 style="color: #202124; margin-top: 0;">🛠️ Technical Architecture</h4>
            <div style="margin-top: 15px;">
                <p style="margin-bottom: 8px;"><b>🧠 Intelligence</b><br><span style="color: #5f6368; font-size: 0.9rem;">Gemini 1.5 Pro (Vision)</span></p>
                <p style="margin-bottom: 8px;"><b>🤖 Orchestration</b><br><span style="color: #5f6368; font-size: 0.9rem;">LangChain SQL Agent</span></p>
                <p style="margin-bottom: 8px;"><b>💾 Database</b><br><span style="color: #5f6368; font-size: 0.9rem;">SQLite (Simulating Firestore)</span></p>
                <p style="margin-bottom: 0px;"><b>💳 Delivery</b><br><span style="color: #5f6368; font-size: 0.9rem;">Google Wallet API</span></p>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # --- TEAM INFO ---
        st.markdown("### Team Details")
        st.markdown("**Developer:** Goutham A.S")
        st.markdown("**contact:** gouthamas369@gmail.com")
        
        # Optional: Add logo here if desired
        # st.image("images/raseed_logo.png", width=100)

about_us()