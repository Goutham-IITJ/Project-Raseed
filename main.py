import streamlit as st
from utilities.home import home_page
# from utilities.authentication import google_auth # Commented out for demo

# --- RASEED CONFIGURATION ---
st.set_page_config(layout="wide", page_title='Project Raseed', page_icon='images/invoicegpt_icon.png')
st.logo("images/invoicegpt_logo.png", icon_image="images/invoicegpt_icon.png")

# --- LOGIN BYPASS (FOR INTERVIEW DEMO) ---
if 'connected' not in st.session_state:
    st.session_state['connected'] = True
    st.session_state['user_info'] = {
        "email": "interview@raseed.ai",
        "name": "Raseed User",
        "picture": "None"
    }

def about():
    home_page()

def exit_app():
    # Simulate logout
    st.session_state['connected'] = False
    st.rerun()

# --- NAVIGATION SETUP ---
logout_page = st.Page(exit_app, title="Log out", icon=":material/logout:")
settings = st.Page("navigation_pages/settings.py", title="Settings", icon=":material/settings:")
view_invoices = st.Page("navigation_pages/invoice_history.py", title="Recent Receipts", icon=":material/receipt:") # Renamed for Raseed
view_invoice_database = st.Page("navigation_pages/my_database.py", title="Raseed Database", icon=":material/database:")
chat_with_ai = st.Page("navigation_pages/ai_chat.py", title="Ask Raseed", icon=":material/chat:") # Renamed
about_page = st.Page(about, title="Dashboard", icon=":material/dashboard:") # Renamed
manual_entry_page = st.Page("navigation_pages/manual_entry.py", title="Manual Entry", icon=":material/edit:")

about_us_page = st.Page("navigation_pages/about_us.py", title="About Project", icon=":material/info:")
contact_us_page = st.Page("navigation_pages/contact_us.py", title="Contact Dev", icon=":material/mail:")

account_pages = [settings, logout_page]
invoice_pages = [about_page, view_invoices, view_invoice_database, chat_with_ai, manual_entry_page]
learn_more_pages = [about_us_page, contact_us_page]

page_dict = {}

if st.session_state.get('connected', False):
    page_dict["Raseed App"] = invoice_pages
    pg = st.navigation(page_dict | {"Info": learn_more_pages} | {f"Account": account_pages})
else:
    # Login screen fallback (won't be seen often due to bypass)
    pg = st.navigation([st.Page(about)])

pg.run()