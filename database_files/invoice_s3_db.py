import os
import shutil
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# Create a local folder for uploads if it doesn't exist
UPLOAD_DIR = "uploaded_invoices"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

def upload_to_s3(file_object, filename, user_email):
    # We are simulating S3 by saving locally
    try:
        # Create a user-specific folder
        user_folder = os.path.join(UPLOAD_DIR, user_email)
        if not os.path.exists(user_folder):
            os.makedirs(user_folder)
            
        file_path = os.path.join(user_folder, filename)
        
        # Save the file locally
        with open(file_path, "wb") as f:
            f.write(file_object.getbuffer())
            
        return file_path
    except Exception as e:
        st.error(f"Error saving file locally: {e}")
        return None

def remove_user_files_from_s3(user_email):
    try:
        user_folder = os.path.join(UPLOAD_DIR, user_email)
        if os.path.exists(user_folder):
            shutil.rmtree(user_folder)
    except Exception as e:
        st.error(f"Error deleting local files: {e}")