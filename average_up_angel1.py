from SmartApi import SmartConnect
import time

from datetime import datetime
import os



#import logging
from trade_utils import removeFile,convert_to_time_obj,is_within_time_range,get_live_price,place_order,download_and_map_symbols,read_and_decrypt_token
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


# Define trading parameters for short selling
initial_position_size = 10  # Number of shares to sell initially
sell_increment_pct = 0.1 / 100  # Sell more after a 0.1% price rise
profit_target_pct = 1.0 / 100  # Cover when 0.7% profit is achieved (price drop)
stop_loss_pct = 0.5 / 100  # Stop loss at 0.35% price rise
initial_entering_price = 1053  # Initial price to start short selling




# Configure the logging
logging.basicConfig(
    filename='app-'+symbol+'.log',  # Name of the log file
    level=logging.DEBUG,  # Minimum level of messages to log
    format='%(asctime)s - %(levelname)s - %(message)s'  # Format of the log messages
)

# Begin average up short selling strategy
def beginAverageUpShort(client,symbols_map):
    global capital, positions, avg_price, total_pnl
    try:
        while True:
            start = convert_to_time_obj(start_time)
            end = convert_to_time_obj(end_time)

            if is_within_time_range(start, end):
                logging.info("Within trading hours... executing Average Up Short Selling strategy")
                current_price = get_live_price(client,symbols_map)
                if current_price is None:
                    logging.info("Error fetching price. Retrying...")
                    time.sleep(1)
                    continue

                logging.info(f"Current price for {symbol}: {current_price:.2f}, Average price: {avg_price}, Positions: {positions}")

                # Short sell more if price increases and it's above the entry price
                if (positions == 0 and current_price >= initial_entering_price) or (positions > 0 and current_price > avg_price * (1 + sell_increment_pct)):
                    logging.info('Averaging up, placing short sell order...')
                    order_id = place_order(client,'SELL', initial_position_size, current_price,symbols_map)
                    if order_id:
                        positions += initial_position_size
                        avg_price = ((avg_price * (positions - initial_position_size)) + (current_price * initial_position_size)) / positions
                        logging.info(f"Short sold {initial_position_size} shares at {current_price:.2f}, Total positions: {positions}, Avg price: {avg_price:.2f}")

                # Profit target reached (cover short position)
                if positions > 0 and current_price <= avg_price * (1 - profit_target_pct):
                    logging.info('Placing buy order, profit target percentage reached...')
                    order_id = place_order(client,'BUY', positions, current_price,symbols_map)
                    if order_id:
                        pnl = positions * (avg_price - current_price)  # Profit in short selling
                        total_pnl += pnl
                        capital += positions * avg_price
                        logging.info(f"Covered {positions} shares at {current_price:.2f}, PnL: {pnl:.2f}, Total capital: {capital:.2f}")
                        positions = 0
                        avg_price = 0

                # Stop loss triggered
                if positions > 0 and current_price >= avg_price * (1 + stop_loss_pct):
                    logging.info('Stop loss triggered, covering all positions.')
                    order_id = place_order(client,'BUY', positions, current_price,symbols_map)
                    if order_id:
                        pnl = positions * (avg_price - current_price)
                        total_pnl += pnl
                        capital += positions * avg_price
                        logging.info(f"Covered {positions} shares at {current_price:.2f} due to stop loss. PnL: {pnl:.2f}, Total capital: {capital:.2f}")
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
        final_pnl = positions * (avg_price - current_price)
        total_pnl += final_pnl
        capital += positions * avg_price
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
    beginAverageUpShort(client,symbols_map)
except Exception as e:
    logging.info(f"Login error: {e}")
    exit()
