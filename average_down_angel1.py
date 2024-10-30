from SmartApi import SmartConnect
import time

from datetime import datetime
import os



#import logging
from trade_utils import *
from __init__ import *


logging.info("In module average_down")

# Initialize tracking variables
capital = initial_capital
positions = 0
avg_price = 0
total_pnl = 0





# Function to remove a file if it exists
def removeTokenFiles():
    removeFile(keyfile)
    removeFile(jwtTokenFile)
    removeFile(feedTokenFile)
    removeFile(refreshTokenFile)

def beginAverageDown(client,symbols_map):
# Real-time trading logic
    global capital, positions, avg_price, total_pnl,start_time,end_time
    try:
        while True:
           
            start = convert_to_time_obj(start_time)
            end = convert_to_time_obj(end_time)

            if is_within_time_range(start, end):
                logging.info("Within trading hours .... executing Average down algo strategy")
                current_price = get_live_price(client,symbols_map)
                if current_price is None:
                    logging.info("Error fetching price. Retrying...")
                    time.sleep(1)
                    continue

                logging.info(f"Current price for {symbol}: {current_price:.2f} , Average price:{avg_price}, Position:{positions}")

                # Simulate average down buying strategy
                if (positions == 0 and current_price <= entry_price) or (positions > 0 and current_price < avg_price * (1 - buy_increment_pct)):
                    if capital >= current_price * initial_position_size:
                        logging.info('Averaging down, Placing buy order...')
                        order_id = place_order(client,'BUY', initial_position_size, current_price,symbols_map)
                        if order_id:
                            positions += initial_position_size
                            capital -= current_price * initial_position_size
                            avg_price = ((avg_price * (positions - initial_position_size)) + (current_price * initial_position_size)) / positions
                            logging.info(f"Bought {initial_position_size} shares at {current_price:.2f}, Total positions: {positions}, Avg price: {avg_price:.2f}")

                # Profit target reached
                if positions > 0 and current_price >= avg_price * (1 + profit_target_pct):
                    logging.info('Placing sell order, profit target percentage reached...')
                    order_id = place_order(client,'SELL', positions, current_price,symbols_map)
                    if order_id:
                        pnl = positions * (current_price - avg_price)
                        total_pnl += pnl
                        capital += positions * current_price
                        logging.info(f"Sold {positions} shares at {current_price:.2f}, PnL: {pnl:.2f}, Total capital: {capital:.2f}")
                        positions = 0
                        avg_price = 0

                # Stop loss triggered
                if positions > 0 and current_price <= avg_price * (1 - stop_loss_pct):
                    logging.info('Stop loss triggered, selling all positions.')
                    order_id = place_order(client,'SELL', positions, current_price,symbols_map)
                    if order_id:
                        pnl = positions * (current_price - avg_price)
                        total_pnl += pnl
                        capital += positions * current_price
                        logging.info(f"Sold {positions} shares at {current_price:.2f} due to stop loss. PnL: {pnl:.2f}, Total capital: {capital:.2f}")
                        positions = 0
                        avg_price = 0

                time.sleep(LIVE_FEED_INTERVAL)
            else:
                logging.info("Outside trading hours")
                break

    except KeyboardInterrupt:
        logging.info("Trading stopped manually")

    # Final PnL if any positions remain
    if positions > 0 and current_price:
        final_pnl = positions * (current_price - avg_price)
        total_pnl += final_pnl
        capital += positions * current_price
        logging.info(f"Mark-to-market on remaining position: {final_pnl:.2f}")
        logging.info(f"Total Profit/Loss: {total_pnl:.2f}")



# Generate session (TOTP login) and start algo strategy 
try:
     # Initialize Angel One SmartAPI client
    
    client = SmartConnect(api_key=creds['api_key'])
    if not os.path.exists(jwtTokenFile):
        
        logging.info('Generating token')               
        data = client.generateSession(creds['client_id'], creds['password'], creds['totp_key'])
        refreshToken = data['data']['refreshToken']
        response = client.generateToken(refreshToken)
        jwtToken=response['data']['jwtToken']
        feedToken=response['data']['feedToken']
        generate_key(keyfile)
        encrypt_and_persist_token(jwtToken, jwtTokenFile, keyfile)
        encrypt_and_persist_token(feedToken, feedTokenFile, keyfile)
        encrypt_and_persist_token(refreshToken, refreshTokenFile, keyfile)
        client.setSessionExpiryHook(removeTokenFiles)

    else :
        jwtToken = read_and_decrypt_token(keyfile, jwtTokenFile)
        feedToken = read_and_decrypt_token(keyfile, feedTokenFile)
        refreshToken = read_and_decrypt_token(keyfile, refreshTokenFile)
        client.setAccessToken(jwtToken)
        client.setFeedToken(feedToken)
        client.setRefreshToken(refreshToken)
        logging.info('Token already generated')   
    
    logging.info("Logged in successfully")
    #load symbols and token map
    symbols_map=download_and_map_symbols()
    beginAverageDown(client,symbols_map)
except Exception as e:
    logging.info(f"Login error: {e}")
    exit()