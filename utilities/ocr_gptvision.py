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
# Using the stable model from your available list
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def ocr_gpt(file_path):
    # Retry configuration
    max_retries = 3
    retry_delay = 5

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

            # 2. Call Gemini
            # Use 'gemini-1.5-flash' or 'gemini-flash-latest' for stability
            model = genai.GenerativeModel('gemini-2.5-flash')
            
            prompt = """
            You are an expert financial analyst for Project Raseed. 
            Extract data from this receipt.
            
            Format output strictly as a JSON object. No Markdown.
            
            Keys required:
            invoice_number, invoice_date (YYYY-MM-DD), due_date (YYYY-MM-DD), 
            seller_information, buyer_information, purchase_order_number, 
            
            # ITEMS SECTION (CRITICAL)
            products_services (Return as a JSON LIST of strings), 
            quantities (Return as a JSON LIST of numbers), 
            unit_prices (Return as a JSON LIST of numbers), 
            
            # TOTALS
            subtotal, service_charges, net_total, discount, tax, tax_rate, 
            shipping_costs, grand_total, currency, payment_terms, payment_method, 
            bank_information, invoice_notes, shipping_address, billing_address,
            
            # CATEGORY
            category (Classify as one of: Groceries, Dining, Transport, Shopping, Utilities, Entertainment, Health, Other)

            If a value is not found, use null. 
            """

            response = model.generate_content([prompt, image_parts[0]])
            
            # 3. Clean and Parse Response
            # Handle cases where Gemini wraps JSON in markdown code blocks
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            
            try:
                invoice_dict = json.loads(clean_text)
            except json.JSONDecodeError:
                # Fallback: Try to find the first { and last }
                start = clean_text.find('{')
                end = clean_text.rfind('}') + 1
                if start != -1 and end != -1:
                    invoice_dict = json.loads(clean_text[start:end])
                else:
                    st.error("Failed to parse AI response. Try again.")
                    return

            # 4. Robust Data Normalization
            def normalize_to_list(val, dtype=str):
                """Handles both JSON Arrays (Lists) and Comma-Separated Strings safely."""
                if val is None: return []
                
                # If it's already a list (e.g. ["Apple", "Banana"]), just cast types
                if isinstance(val, list):
                    return [dtype(x) for x in val if x is not None]
                
                # If it's a string (e.g. "Apple, Banana"), split it
                if isinstance(val, str):
                    if val.strip() == "" or val.lower() == "null": return []
                    # Remove accidental brackets like "['A', 'B']"
                    clean_val = val.replace('[', '').replace(']', '').replace("'", "").replace('"', "")
                    return [dtype(x.strip()) for x in clean_val.split(',') if x.strip()]
                
                return []

            items = normalize_to_list(invoice_dict.get('products_services'), str)
            quantities = normalize_to_list(invoice_dict.get('quantities'), int) 
            prices = normalize_to_list(invoice_dict.get('unit_prices'), float)

            # Ensure lists are same length to avoid zip errors
            # Pad with 1 (qty) or 0 (price) if missing
            max_len = len(items)
            while len(quantities) < max_len: quantities.append(1)
            while len(prices) < max_len: prices.append(0.0)

            # 5. Insert into DB
            user_email = st.session_state.get('user_info', {}).get('email', 'test_user@localhost')
            insert_invoice_and_items(invoice_dict, file_path, items, quantities, prices, user_email) 
            
            st.success(f"Receipt processed! Category: {invoice_dict.get('category', 'Unknown')}")
            return 

        except exceptions.ResourceExhausted:
            st.warning(f"Rate limit hit. Retrying in {retry_delay}s... ({attempt+1}/{max_retries})")
            time.sleep(retry_delay)
            continue 

        except Exception as e:
            st.error(f"Error in Raseed Intelligence Engine: {e}")
            traceback.print_exc()
            return