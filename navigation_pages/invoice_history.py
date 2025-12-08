import streamlit as st
from database_files.sqlite_db import query_db, delete_data, create_connection, sanitize_email
import os
import pandas as pd
import datetime
import plotly.express as px
from utilities.wallet_helper import create_jwt_link, create_class_if_not_exists

# --- LOCAL CONFIGURATION ---
UPLOAD_DIR = "uploaded_invoices"
supported_extensions = ('.jpg', '.jpeg', '.png', '.pdf')

st.header("Spending Dashboard")

# Helper to get user folder
user_email = st.session_state['user_info'].get('email')
user_folder = os.path.join(UPLOAD_DIR, user_email)

if not os.path.exists(user_folder):
    os.makedirs(user_folder)

# --- WALLET SETUP ---
# Ensure the Wallet Class exists when the page loads
if "wallet_class_checked" not in st.session_state:
    try:
        create_class_if_not_exists()
        st.session_state["wallet_class_checked"] = True
    except Exception as e:
        # Don't crash if wallet creds are missing (just print warning)
        print(f"Wallet Init Warning: {e}")

# --- ANALYTICS SECTION ---
try:
    conn = create_connection()
    sanitized_email = sanitize_email(user_email)
    
    # Fetch spending by category from DB
    df_chart = pd.read_sql_query(
        f"SELECT category, SUM(grand_total) as total FROM invoices_{sanitized_email} GROUP BY category", 
        conn
    )
    conn.close()

    if not df_chart.empty:
        col_chart1, col_chart2 = st.columns([2, 1])
        
        with col_chart1:
            # Interactive Donut Chart
            fig = px.pie(
                df_chart, 
                values='total', 
                names='category', 
                title='Spending by Category',
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.G10 
            )
            fig.update_layout(height=350, margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)
        
        with col_chart2:
            # Key Metrics
            total_spend = df_chart['total'].sum()
            # Find top category safely
            if not df_chart.empty:
                top_cat_row = df_chart.loc[df_chart['total'].idxmax()]
                top_cat = top_cat_row['category']
            else:
                top_cat = "N/A"
                
            st.metric("Total Spent", f"${total_spend:,.2f}")
            st.metric("Top Category", top_cat)
            
except Exception as e:
    # Fail silently if DB is empty or table doesn't exist yet
    pass

st.divider()
st.subheader("Recent Receipts")

# --- DIALOGS ---

@st.dialog(title="Receipt Preview", width="large")
def preview(file_path):
    if os.path.exists(file_path):
        if file_path.lower().endswith('.pdf'):
            st.info("PDF preview not supported in local demo mode.")
        else:
            st.image(file_path)
    else:
        st.error("File not found.")

@st.dialog(title="Extracted Data", width="large")
def invoice_attributes(filename):
    # Query the local SQLite DB
    invoice_data, line_items_data = query_db(filename, user_email)

    if invoice_data:
        st.subheader("Receipt Details")
        
        # Updated Columns to match DB Schema (including Category)
        invoice_columns = [
            'ID', 'File Name', 'Category', 'Invoice #', 'Date', 'Due Date', 'Seller',
            'Buyer', 'PO #', 'Subtotal', 'Service Charge', 'Net',
            'Discount', 'Tax', 'Rate', 'Shipping', 'Total', 'Currency', 'Terms',
            'Method', 'Bank', 'Notes', 'Ship Addr', 'Bill Addr'
        ]
        
        # Create DataFrame safely
        if len(invoice_data) == len(invoice_columns):
             df = pd.DataFrame([invoice_data], columns=invoice_columns)
        else:
             df = pd.DataFrame([invoice_data])
             
        st.dataframe(df.T) # Transposed for easier reading

        # --- WALLET BUTTON SECTION ---
        st.divider()
        col_wal1, col_wal2 = st.columns([1, 2])
        
        with col_wal1:
            st.markdown("### 📲 Actions")
        
        with col_wal2:
            # Generate the specific pass link for THIS receipt
            try:
                if st.button("Generate Wallet Pass", key="gen_pass"):
                    with st.spinner("Minting Pass..."):
                        wallet_link = create_jwt_link(invoice_data, line_items_data)
                        
                        # Show the official "Add to Google Wallet" button
                        st.success("Pass Ready!")
                        st.link_button("Add to Google Wallet", wallet_link, type="primary")
                        st.caption("Click to save this receipt to your phone.")
                        
            except Exception as e:
                st.error(f"Wallet Error: {e}")
                st.caption("Check your wallet_key.json and Issuer ID.")

    if line_items_data:
        st.divider()
        st.subheader("Line Items")
        line_items_columns = ['ID', 'File Name', 'Invoice ID', 'Product', 'Qty', 'Price']
        df_items = pd.DataFrame(line_items_data, columns=line_items_columns)
        st.dataframe(df_items)

@st.dialog(title="Delete Receipt", width="small")
def delete_invoice(file_path, name):
    st.warning(f"Delete {name}?")
    if st.button("Yes, Delete"):
        delete_data(name, user_email)
        if os.path.exists(file_path):
            os.remove(file_path)
        st.success("Deleted!")
        st.rerun()

# --- LIST LOCAL FILES ---
try:
    if os.path.exists(user_folder):
        files = os.listdir(user_folder)
        files = [f for f in files if f.lower().endswith(supported_extensions)]
    else:
        files = []
    
    if files:
        # Table Header
        col1, col2, col3 = st.columns([3, 2, 3])
        col1.caption("Receipt Name")
        col2.caption("Date Processed")
        col3.caption("Actions")
        st.divider()
        
        for filename in files:
            file_path = os.path.join(user_folder, filename)
            mod_time = os.path.getmtime(file_path)
            date_str = datetime.datetime.fromtimestamp(mod_time).strftime('%Y-%m-%d %H:%M')
            
            c1, c2, c3 = st.columns([3, 2, 3], vertical_alignment='center')
            c1.write(f"📄 {filename}")
            c2.write(date_str)
            
            with c3:
                sc1, sc2, sc3 = st.columns(3)
                if sc1.button("👁️", key=f"view_{filename}", help="View Image"):
                    preview(file_path)
                # The Data button now opens the dialog with the Wallet Integration
                if sc2.button("📊", key=f"data_{filename}", help="View Data & Wallet"):
                    invoice_attributes(filename)
                if sc3.button("🗑️", key=f"del_{filename}", help="Delete"):
                    delete_invoice(file_path, filename)
            st.markdown("---")
    else:
        st.info("No receipts found. Go to Home to upload one!")

except Exception as e:
    st.error(f"Error reading local folder: {e}")