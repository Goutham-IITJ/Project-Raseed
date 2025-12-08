import json
import time
import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request
import jwt  # pip install pyjwt

# --- CONFIGURATION ---
# REPLACE THESE WITH YOUR ACTUAL DETAILS
ISSUER_ID = '3388000000023034288'  # <--- PASTE YOUR ISSUER ID HERE
SERVICE_ACCOUNT_FILE = 'wallet_key.json' # <--- ENSURE THIS FILE IS IN YOUR FOLDER

def get_authenticated_creds():
    """Authenticates using the Service Account."""
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=['https://www.googleapis.com/auth/wallet_object.issuer']
    )
    creds.refresh(Request())
    return creds

def create_class_if_not_exists():
    """
    Creates the 'Raseed Receipt' template (Class) in Google Wallet.
    Run this once to define what the pass looks like (Logo, Header, etc).
    """
    class_id = f'{ISSUER_ID}.raseed_receipt_v1'
    creds = get_authenticated_creds()
    
    # Check if class exists
    url = f'https://walletobjects.googleapis.com/walletobjects/v1/genericClass/{class_id}'
    headers = {'Authorization': f'Bearer {creds.token}'}
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        return class_id  # Already exists
        
    # Define the Class (The Template)
    new_class = {
        "id": class_id,
        "classTemplateInfo": {
            "cardBarcodeSectionDetails": {
                "sectionHeader": "Scan Receipt"
            },
            "cardTemplateOverride": {
                "cardRowTemplateInfos": [
                    {
                        "twoItems": {
                            "startItem": {
                                "firstValue": {"fields": [{"fieldPath": "object.textModulesData['amount']"}]}
                            },
                            "endItem": {
                                "firstValue": {"fields": [{"fieldPath": "object.textModulesData['date']"}]}
                            }
                        }
                    }
                ]
            }
        },
        "imageModulesData": [
            {
                "mainImage": {
                    # Use a publicly hosted URL for the logo. Localhost won't work.
                    "sourceUri": {"uri": "https://cdn-icons-png.flaticon.com/512/2534/2534863.png"}
                },
                "id": "logo_module"
            }
        ]
    }
    
    # Send to Google
    post_url = 'https://walletobjects.googleapis.com/walletobjects/v1/genericClass'
    resp = requests.post(post_url, json=new_class, headers=headers)
    
    if resp.status_code != 200:
        raise Exception(f"Failed to create class: {resp.text}")
        
    return class_id

def create_jwt_link(invoice_data, line_items):
    """
    Generates a Signed JWT Link.
    invoice_data: Tuple from DB (filename, category, invoice_num, date, ...)
    line_items: List of tuples from DB
    """
    
    # 1. Prepare Data
    # Mapping indices based on your sqlite_db.py schema:
    # 0:id, 1:filename, 2:category, 3:inv_num, 4:date, ... 15:grand_total
    
    merchant_name = invoice_data[6] or "Retailer" # Seller Info
    date_str = str(invoice_data[4]) or "Today"    # Invoice Date
    total_price = str(invoice_data[16]) or "0.00" # Grand Total (index 16 in new schema)
    category = invoice_data[2] or "Expense"       # Category
    
    # Unique ID for this specific pass object
    object_id = f"{ISSUER_ID}.receipt_{invoice_data[0]}_{int(time.time())}"
    class_id = f'{ISSUER_ID}.raseed_receipt_v1'

    # Build List of Items for the Pass
    items_text = ""
    for item in line_items:
        # item: (id, filename, inv_id, product, qty, price)
        items_text += f"{item[4]}x {item[3]} (${item[5]})\n"
    
    if not items_text: items_text = "No item details available."

    # 2. Define the Object (The specific receipt)
    new_object = {
        "id": object_id,
        "classId": class_id,
        "logo": {
            "sourceUri": {"uri": "https://cdn-icons-png.flaticon.com/512/2534/2534863.png"},
            "contentDescription": {"defaultValue": {"language": "en-US", "value": "Logo"}}
        },
        "cardTitle": {
            "defaultValue": {
                "language": "en-US",
                "value": merchant_name
            }
        },
        "header": {
            "defaultValue": {
                "language": "en-US",
                "value": f"Total: ${total_price}"
            }
        },
        "hexBackgroundColor": "#4285F4", # Google Blue background
        "textModulesData": [
            {
                "id": "amount",
                "header": "Total",
                "body": f"${total_price}"
            },
            {
                "id": "date",
                "header": "Date",
                "body": date_str
            },
            {
                "id": "category",
                "header": "Category",
                "body": category
            },
            {
                "id": "items",
                "header": "Itemized List",
                "body": items_text[:600] # Truncate if too long
            }
        ]
    }

    # 3. Create the JWT Payload
    service_account_info = json.load(open(SERVICE_ACCOUNT_FILE))
    
    claims = {
        "iss": service_account_info['client_email'],
        "aud": "google",
        "typ": "savetowallet",
        "iat": int(time.time()),
        "payload": {
            "genericObjects": [new_object]
        }
    }

    # 4. Sign the Token
    token = jwt.encode(
        claims, 
        service_account_info['private_key'], 
        algorithm='RS256'
    )

    return f"https://pay.google.com/gp/v/save/{token}"