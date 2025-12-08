import streamlit as st
import os
from utilities.home import home_page

# --- PAGE CONFIG ---
st.set_page_config(layout="wide", page_title='Project Raseed', page_icon='💳')

# --- SMART LOGO FINDER ---
logo_path = None
# Check exact filenames. Add your specific filename here if different.
possible_paths = [
    "images/raseedlogo.png",       
    "images/Raseed_Logo.png",       
    "images/logo.png",
    "images/invoicegpt_logo.png",
    "images/invoicegpt_logo_full.png"
]

for path in possible_paths:
    if os.path.exists(path):
        logo_path = path
        break

# --- GOOGLE MATERIAL CSS & LOGO HACK ---
st.markdown("""
    <style>
        /* Google Fonts */
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');
        html, body, [class*="css"] { font-family: 'Roboto', sans-serif; }
        
        /* Sidebar Background */
        [data-testid="stSidebar"] {
            background-color: #F8F9FA;
        }

        /* --- AGGRESSIVE LOGO SIZING --- */
        /* Forces the container to expand */
        [data-testid="stSidebarHeader"] {
            padding-bottom: 0px !important;
        }
        [data-testid="stLogo"] {
            height: auto !important;
            width: auto !important;
            max-width: 100% !important;
        }
        /* Forces the image itself to be big */
        [data-testid="stLogo"] img {
            height: auto !important;
            width: 220px !important; /* Adjust this px value to control size */
            max-width: 90% !important;
            margin-bottom: 10px;
        }

        /* Button Styling */
        div.stButton > button {
            border-radius: 24px;
            padding: 10px 24px;
            font-weight: 500;
            border: none;
            box-shadow: 0 1px 2px rgba(60,64,67,0.3);
            background-color: #1A73E8;
            color: white;
            transition: all 0.2s;
        }
        div.stButton > button:hover {
            box-shadow: 0 4px 8px rgba(60,64,67,0.15);
            background-color: #1557B0; 
            transform: translateY(-1px);
        }
    </style>
""", unsafe_allow_html=True)

# --- SET LOGO ---
if logo_path:
    st.logo(logo_path, icon_image=None)
else:
    # If no logo found, show text (Debug check)
    st.sidebar.warning("Logo file not found in 'images/' folder.")

# --- LOGIN BYPASS ---
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
    st.session_state['connected'] = False
    st.rerun()

# --- NAVIGATION ---
logout_page = st.Page(exit_app, title="Log out", icon=":material/logout:")
settings = st.Page("navigation_pages/settings.py", title="Settings", icon=":material/settings:")
view_invoices = st.Page("navigation_pages/invoice_history.py", title="History", icon=":material/history:") 
view_invoice_database = st.Page("navigation_pages/my_database.py", title="Database", icon=":material/database:")
chat_with_ai = st.Page("navigation_pages/ai_chat.py", title="Ask Agent", icon=":material/smart_toy:") 
about_page = st.Page(about, title="Home", icon=":material/home:") 
manual_entry_page = st.Page("navigation_pages/manual_entry.py", title="Edit", icon=":material/edit:")
about_us_page = st.Page("navigation_pages/about_us.py", title="About", icon=":material/info:")
contact_us_page = st.Page("navigation_pages/contact_us.py", title="Contact", icon=":material/mail:")

account_pages = [settings, logout_page]
invoice_pages = [about_page, view_invoices, view_invoice_database, chat_with_ai, manual_entry_page]
learn_more_pages = [about_us_page, contact_us_page]

page_dict = {}

if st.session_state.get('connected', False):
    page_dict["Apps"] = invoice_pages
    pg = st.navigation(page_dict | {"Info": learn_more_pages} | {f"Account": account_pages})
else:
    pg = st.navigation([st.Page(about)])

pg.run()