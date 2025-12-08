import json
import time
import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request
import jwt
import streamlit as st
import os

# --- CONFIGURATION ---
ISSUER_ID = '3388000000023034288'  # Ensure this matches your actual Issuer ID

def get_service_account_info():
    """
    Smart loader: Checks Streamlit Secrets first (Cloud), then local file (Localhost).
    """
    # 1. Try Cloud Secrets (Streamlit Cloud)
    if "gcp_service_account" in st.secrets:
        return st.secrets["gcp_service_account"]
    
    # 2. Try Local File (Localhost)
    file_path = 'wallet_key.json'
    if os.path.exists(file_path):
        return json.load(open(file_path))
        
    return None

def get_authenticated_creds():
    """Authenticates using the Service Account Info."""
    info = get_service_account_info()
    if not info:
        raise Exception("Service Account Credentials not found! Check st.secrets or wallet_key.json")

    creds = service_account.Credentials.from_service_account_info(
        info,
        scopes=['https://www.googleapis.com/auth/wallet_object.issuer']
    )
    creds.refresh(Request())
    return creds

def create_class_if_not_exists():
    class_id = f'{ISSUER_ID}.raseed_receipt_v1'
    creds = get_authenticated_creds()
    
    url = f'https://walletobjects.googleapis.com/walletobjects/v1/genericClass/{class_id}'
    headers = {'Authorization': f'Bearer {creds.token}'}
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        return class_id
        
    new_class = {
        "id": class_id,
        "classTemplateInfo": {
            "cardBarcodeSectionDetails": {"sectionHeader": "Scan Receipt"},
            "cardTemplateOverride": {
                "cardRowTemplateInfos": [{
                    "twoItems": {
                        "startItem": {"firstValue": {"fields": [{"fieldPath": "object.textModulesData['amount']"}]}},
                        "endItem": {"firstValue": {"fields": [{"fieldPath": "object.textModulesData['date']"}]}}
                    }
                }]
            }
        },
        "imageModulesData": [{
            "mainImage": {"sourceUri": {"uri": "https://cdn-icons-png.flaticon.com/512/2534/2534863.png"}},
            "id": "logo_module"
        }]
    }
    
    requests.post(
        'https://walletobjects.googleapis.com/walletobjects/v1/genericClass',
        json=new_class,
        headers=headers
    )
    return class_id

def create_jwt_link(invoice_data, line_items):
    merchant_name = invoice_data[6] or "Retailer"
    date_str = str(invoice_data[4]) or "Today"
    total_price = str(invoice_data[16]) or "0.00"
    category = invoice_data[2] or "Expense"
    
    object_id = f"{ISSUER_ID}.receipt_{invoice_data[0]}_{int(time.time())}"
    class_id = f'{ISSUER_ID}.raseed_receipt_v1'

    items_text = ""
    for item in line_items:
        items_text += f"{item[4]}x {item[3]} (${item[5]})\n"
    if not items_text: items_text = "No item details available."

    new_object = {
        "id": object_id,
        "classId": class_id,
        "logo": {
            "sourceUri": {"uri": "https://cdn-icons-png.flaticon.com/512/2534/2534863.png"},
            "contentDescription": {"defaultValue": {"language": "en-US", "value": "Logo"}}
        },
        "cardTitle": {"defaultValue": {"language": "en-US", "value": merchant_name}},
        "header": {"defaultValue": {"language": "en-US", "value": f"Total: ${total_price}"}},
        "hexBackgroundColor": "#4285F4",
        "textModulesData": [
            {"id": "amount", "header": "Total", "body": f"${total_price}"},
            {"id": "date", "header": "Date", "body": date_str},
            {"id": "category", "header": "Category", "body": category},
            {"id": "items", "header": "Itemized List", "body": items_text[:600]}
        ]
    }

    service_account_info = get_service_account_info()
    
    claims = {
        "iss": service_account_info['client_email'],
        "aud": "google",
        "typ": "savetowallet",
        "iat": int(time.time()),
        "payload": {"genericObjects": [new_object]}
    }

    token = jwt.encode(claims, service_account_info['private_key'], algorithm='RS256')
    return f"https://pay.google.com/gp/v/save/{token}"