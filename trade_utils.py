# trading_utils.py

#import logging
import time
from datetime import datetime
from cryptography.fernet import Fernet
import pytz
import requests
from __init__ import *
import json

# Generate and save the key (you should store this key securely)
def generate_key(file_path):
    key = Fernet.generate_key()
    with open(file_path, "wb") as key_file:
        key_file.write(key)

# Load the key from file
def load_key(file_path):
    with open(file_path, "rb") as key_file:
        return key_file.read()

# Read from file and decrypt the token
def read_and_decrypt_token(key_file, token_file):
    key = load_key(key_file)
    cipher_suite = Fernet(key)

    with open(token_file, "rb") as file:
        encrypted_token = file.read()

    decrypted_token = cipher_suite.decrypt(encrypted_token).decode()
    return decrypted_token

# Encrypt the token and persist it to a file
def encrypt_and_persist_token(token, token_file, key_file):
    key = load_key(key_file)
    cipher_suite = Fernet(key)
    encrypted_token = cipher_suite.encrypt(token.encode())

    with open(token_file, "wb") as file:
        file.write(encrypted_token)


# Function to remove a file if it exists
def removeFile(file_path):
    if os.path.exists(file_path):
        os.remove(file_path)
        logging.info(f"File {file_path} removed successfully.")
    else:
        logging.info(f"File {file_path} does not exist.")    




def download_and_map_symbols():
    # Step 1: Define the API URL
    url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
    
    # Step 2: Download the JSON data from the URL
    response = requests.get(url)
    if response.status_code == 200:
        # Save JSON to current folder
        with open("OpenAPIScripMaster.json", "w") as f:
            f.write(response.text)
        logging.info("JSON file downloaded successfully.")
    else:
        logging.info(f"Failed to download JSON: {response.status_code}")
        return

    # Step 3: Load the JSON data
    with open("OpenAPIScripMaster.json", "r") as f:
        data = json.load(f)
    
    # Step 4: Create a map of tradingsymbol -> symboltoken
    symbol_map = {item['symbol']: item['token'] for item in data}
    
    return symbol_map
   



# Get Live Price
def get_live_price(client,symbols_map):
    #global symbols_map,symbol
    logging.info("fetching live price")
    try:
        symbol_token = symbols_map[symbol]
        logging.debug('symbol-token:{symbol_token}')
        feed = client.ltpData("NSE", symbol, symbol_token)  # Adjust token (26000) for your symbol
        logging.debug(f'feed: {feed}')
        return feed['data']['ltp'] if feed and 'data' in feed else None
    except Exception as e:
        logging.info(f"Error fetching live price: {e}")
        return None

# Get Live Price
def get_live_feed(client,symbols_map):
    #global symbols_map,symbol
    logging.info("fetching live price")
    try:
        symbol_token = symbols_map[symbol]
        logging.debug('symbol-token:{symbol_token}')
        feed = client.ltpData("NSE", symbol, symbol_token)  # Adjust token (26000) for your symbol
        logging.debug(f'feed: {feed}')
        return feed if feed and 'data' in feed else None
    except Exception as e:
        logging.info(f"Error fetching live price: {e}")
        return None

# Place Order
def place_order(client,order_type, qty, price,symbols_map):
    
    order_params = {
        "variety": "NORMAL",
        "tradingsymbol": symbol,
        "symboltoken": symbols_map[symbol],  # Adjust token for your symbol
        "transactiontype": order_type,
        "exchange": "NSE",
        "ordertype": "LIMIT",
        "quantity": qty,
        "price": price,
        "producttype": "INTRADAY",
        "duration": "DAY"
    }
    try:
        order_id = client.placeOrder(order_params)
        return order_id
    except Exception as e:
        logging.info(f"Error placing order: {e}")
        return None

# Define time range and timezone
local_timezone = pytz.timezone("Asia/Kolkata")

# Convert the time range to datetime objects with the local timezone
def convert_to_time_obj(time_str):
    return local_timezone.localize(datetime.strptime(time_str, "%H:%M"))

# Check if current time is within the trading window
def is_within_time_range(start, end):
    current_time = datetime.now(local_timezone)
    return start.time() <= current_time.time() <= end.time()




