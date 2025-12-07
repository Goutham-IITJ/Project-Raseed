import base64
import os
import json
import time
import google.generativeai as genai
from google.api_core import exceptions
from database_files.sqlite_db import insert_invoice_and_items
from pdf2image import convert_from_path
from io import BytesIO
import streamlit as st
from dotenv import load_dotenv
import traceback

load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def ocr_gpt(file_path):
    # Retry configuration: Try 3 times, waiting 30 seconds between tries
    max_retries = 3
    retry_delay = 30

    for attempt in range(max_retries):
        try:
            image_parts = []
            image_data = None
            
            # 1. Read File from Local Disk
            if file_path.lower().endswith('.pdf'):
                images = convert_from_path(file_path)
                img_byte_arr = BytesIO()
                images[0].save(img_byte_arr, format='JPEG')
                image_data = img_byte_arr.getvalue()
                image_parts = [{"mime_type": "image/jpeg", "data": image_data}]
            else:
                with open(file_path, "rb") as f:
                    image_data = f.read()
                image_parts = [{"mime_type": "image/jpeg", "data": image_data}]

            if not image_parts or not image_data:
                st.error("Failed to load image data")
                return

            # 2. Call Gemini 2.5 Flash (Confirmed available in your list)
            model = genai.GenerativeModel('gemini-2.5-flash')
            
            prompt = """
            You are an expert receipt scanner for Project Raseed. 
            Extract the following key invoice attributes from the image.
            
            Format your output strictly as a JSON object. Do not include Markdown formatting.
            
            Keys required:
            invoice_number, invoice_date (YYYY-MM-DD), due_date (YYYY-MM-DD), 
            seller_information, buyer_information, purchase_order_number, 
            products_services (comma separated string), 
            quantities (comma separated integers), 
            unit_prices (comma separated numerics), 
            subtotal, service_charges, net_total, discount, tax, tax_rate, 
            shipping_costs, grand_total, currency, payment_terms, payment_method, 
            bank_information, invoice_notes, shipping_address, billing_address.

            If a value is not found, use null or "NULL". 
            Convert percentages to decimals (20% -> 0.2).
            """

            response = model.generate_content([prompt, image_parts[0]])
            
            # 3. Clean and Parse Response
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            invoice_dict = json.loads(clean_text)

            # 4. Format Data for Database
            def clean_split(val, dtype=str):
                if not val or val == "NULL": return []
                return [dtype(x.strip()) for x in str(val).split(',')]

            items = clean_split(invoice_dict.get('products_services'), str)
            quantities = clean_split(invoice_dict.get('quantities'), str) 
            prices = clean_split(invoice_dict.get('unit_prices'), str)

            # 5. Insert into DB
            user_email = st.session_state.get('user_info', {}).get('email', 'test_user@localhost')
            insert_invoice_and_items(invoice_dict, file_path, items, quantities, prices, user_email) 
            
            st.success("Receipt processed successfully!")
            return 

        except exceptions.ResourceExhausted:
            # QUOTA ERROR HANDLER
            if attempt < max_retries - 1:
                st.warning(f"Gemini 2.5 rate limit hit. Cooling down for {retry_delay}s... (Attempt {attempt+1}/{max_retries})")
                time.sleep(retry_delay)
                continue 
            else:
                st.error("Quota exceeded. Please try again in a few minutes.")
                return

        except Exception as e:
            st.error(f"Error in Raseed Intelligence Engine: {e}")
            traceback.print_exc()
            return