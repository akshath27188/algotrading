from __future__ import print_function
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import yfinance as yf
import pandas as pd
import talib as ta
import time as time
import os
from SmartApi import SmartConnect
import numpy as np 
import pickle

import asyncio
import websockets
import json
import pandas as pd
import logging
from datetime import datetime

from trade_utils import *
from __init__ import *
from angel_websocket import *
# Configure the logging
# logging.basicConfig(
#     filename='app-intraday.log',
#     level=logging.DEBUG,
#     format='%(asctime)s - %(levelname)s - %(message)s'
# )

symbol = 'LTFOODS'
holdings = ['ACI', 'GANESHHOUC', 'GIPCL', 'INDIANHUME', 'KARURVYSYA', 
            'LTFOODS', 'MAHSEAMLES', 'MANINDS', 'MANINFRA', 'MOIL', 
            'MOTHERSON', 'NATIONALUM', 'NHPC', 'PARADEEP', 'PENIND', 
            'RECLTD', 'RITES', 'RTNPOWER', 'SBIN', 'SBINEQWETF', 
            'SOUTHBANK', 'UJJIVANSFB', 'YATHARTH', 'YESBANK', 'INDRAMEDCO']


#highest rolling window of the 3 indicators , will also be used to as the timeperiod to process data 
max_timeperiod=20

#rsi,mcad indicator timeperiod
rsi_timeperiod=7
mfastperiod=6
mslowperiod=19
msignalperiod=5

def get_stock_data(ticker, period='1d', interval='5m'):
    try:
        stock_data = yf.download(ticker, period=period, interval=interval)
        if stock_data.empty:
            raise ValueError(f"No data returned for {ticker}")
        stock_data.index.name = 'Date'
        return stock_data
    except Exception as e:
        logging.error(f"Error downloading data for {ticker}: {e}")
        return pd.DataFrame()

def add_intraday_indicators(df):
    df['RSI'] = ta.RSI(df['Close'], rsi_timeperiod=7)
    df['Upper_BB'], df['Middle_BB'], df['Lower_BB'] = ta.BBANDS(df['Close'], max_timeperiod=20)
    df['MACD'], df['MACD_signal'], df['MACD_hist'] = ta.MACD(df['Close'], mfastperiod=6, mslowperiod=19, msignalperiod=5)
    return df

def generate_intraday_signals(df):
    df['Signal'] = None
    for i in range(1, len(df)):
        # Skip if any required values are NaN
        if (np.isnan(df['RSI'].iloc[i]) or
                np.isnan(df['Close'].iloc[i]) or
                np.isnan(df['Upper_BB'].iloc[i]) or
                np.isnan(df['Lower_BB'].iloc[i]) or
                np.isnan(df['MACD'].iloc[i]) or
                np.isnan(df['MACD_signal'].iloc[i])):
            continue

        # Define parameters for oversold/overbought conditions
        rsi_oversold = 25  # Adjusted oversold threshold
        rsi_overbought = 75  # Adjusted overbought threshold

        # Define conditions for signals
        is_oversold_bounce = (df['RSI'].iloc[i] < rsi_oversold and 
                              df['Close'].iloc[i] > df['Lower_BB'].iloc[i] and 
                              df['Close'].iloc[i-1] <= df['Lower_BB'].iloc[i-1])
        
        is_overbought_bounce = (df['RSI'].iloc[i] > rsi_overbought and 
                                df['Close'].iloc[i] < df['Upper_BB'].iloc[i] and 
                                df['Close'].iloc[i-1] >= df['Upper_BB'].iloc[i-1])
        
        is_macd_buy = (df['MACD'].iloc[i] > df['MACD_signal'].iloc[i] and 
                       df['MACD'].iloc[i-1] <= df['MACD_signal'].iloc[i-1])
        
        is_macd_sell = (df['MACD'].iloc[i] < df['MACD_signal'].iloc[i] and 
                        df['MACD'].iloc[i-1] >= df['MACD_signal'].iloc[i-1])

        # Combine conditions to generate signals
        if is_oversold_bounce or is_macd_buy:
            df.loc[df.index[i], 'Signal'] = 'Buy'
        elif is_overbought_bounce or is_macd_sell:
            df.loc[df.index[i], 'Signal'] = 'Sell'

    return df

def execute_intraday_strategy(ticker):
    df = get_stock_data(ticker, period='1d', interval='5m')
    if df.empty:
        logging.warning(f"Skipping {ticker} due to missing data or error")
        return df

    df = add_intraday_indicators(df)
    df = df.dropna(subset=['RSI', 'Upper_BB', 'Lower_BB', 'MACD', 'MACD_signal', 'MACD_hist'])
    df = generate_intraday_signals(df)
    df = df.dropna(subset=['Signal']).reset_index()
    return df[['Date', 'Close', 'RSI', 'Upper_BB', 'Lower_BB', 'MACD', 'MACD_signal', 'MACD_hist', 'Signal']]

def backtest_intraday_strategy(ticker, date, interval='1m', max_timeperiod=15, quantity=1):
    try:
        start_date = pd.to_datetime(date)
        end_date = start_date + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        data = yf.download(ticker, start=start_date, end=end_date, interval=interval)
        print(data)
        if data.empty:
            logging.warning(f"No data found for {ticker} on {date}")
            return pd.DataFrame()

        df = add_intraday_indicators(data)
        df = generate_intraday_signals(df)  # Generate signals once at the start
        timeperiod, position, entry_price, pnl = 15, 0, 0, 0
        for i in range(timeperiod, len(df)):
            # Create a subset of the DataFrame based on the dynamic time period
            df_subset = df.iloc[i - timeperiod:i + 1]

            # Use the last row of df_subset for signal and current price
            signal, current_price = df_subset['Signal'].iloc[-1], df_subset['Close'].iloc[-1]

            # Entry and exit logic
            if signal:
                if signal == 'Buy' and position == 0:
                    position, entry_price = 1, current_price
                elif signal == 'Sell' and position == 1:
                    pnl += (current_price - entry_price) * quantity
                    position = 0
                elif signal == 'Sell' and position == 0:
                    position, entry_price = -1, current_price
                elif signal == 'Buy' and position == -1:
                    pnl += (entry_price - current_price) * quantity
                    position = 0

            # Store the cumulative PnL and signal
            df.loc[df_subset.index[-1], 'PnL'], df.loc[df_subset.index[-1], 'Signal'] = pnl, signal

        return df.dropna(subset=['Signal'])
    except Exception as e:
        logging.error(f"Backtesting error: {e}")
        return pd.DataFrame()

def backtest_intraday_strategy_with_profit_threshold(ticker, date, interval='1m', max_timeperiod=60, quantity=1, profit_threshold=0.002):
    try:
        start_date = pd.to_datetime(date)
        end_date = start_date + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        data = yf.download(ticker, start=start_date, end=end_date, interval=interval)
        print('data: ---',data)
        if data.empty:
            logging.warning(f"No data found for {ticker} on {date}")
            return pd.DataFrame()

        df = add_intraday_indicators(data)
        df = generate_intraday_signals(df)
        timeperiod, position, entry_price, pnl = 15, 0, None, 0
        
        for i in range(timeperiod, len(df)):
            df_subset = df.iloc[i - timeperiod:i + 1]
            
            signal, current_price = df_subset['Signal'].iloc[-1], df_subset['Close'].iloc[-1]
            
            #logging.debug('checking to see if there is a signal')
            # Check if there's a signal and calculate potential profit/loss
            if signal == 'Buy' or signal =='Sell':                
                # Set price difference and threshold condition only if entry_price is defined
                if entry_price is not None:
                    #print("entry_price is not none")
                    logging.debug('entry_price is not none')
                    
                    price_diff = (current_price - entry_price) if position == 1 else (entry_price - current_price)
                    meets_threshold = price_diff / entry_price >= profit_threshold
                    print("price_diff_hold:",price_diff / entry_price)
                else:
                    #print("entry_price is  none")
                    logging.debug('entry_price is none')
                    meets_threshold = True  # First buy or short action doesn't need a threshold check

                # Execute buy/sell logic based on threshold check
                if signal == 'Buy' and position == 0 and meets_threshold:
                    position, entry_price = 1, current_price
                elif signal == 'Sell' and position == 1 and meets_threshold:
                    pnl += (current_price - entry_price) * quantity
                    position, entry_price = 0, None  # Reset entry price after selling
                elif signal == 'Sell' and position == 0 and meets_threshold:
                    position, entry_price = -1, current_price
                elif signal == 'Buy' and position == -1 and meets_threshold:
                    pnl += (entry_price - current_price) * quantity
                    position, entry_price = 0, None  # Reset entry price after covering

            # Update PnL and Signal in the DataFrame
            df.loc[df_subset.index[-1], 'PnL'], df.loc[df_subset.index[-1], 'Signal'] = pnl, signal
            #timeperiod = min(timeperiod + 1, max_timeperiod)
        #df.to_csv('backtest_rsi_bollinger_results.csv', index=True)  # Set index=False if you don’t need the index column in the CSV
    
        return df.dropna(subset=['Signal'])
    except Exception as e:
        logging.error(f"Backtesting error: {e}")
        return pd.DataFrame()


# Global parameters
live_df = []
profit_threshold = 0.01  # Example threshold
quantity = 1  # Quantity to trade
timeperiod = 15  # Indicator period
position, entry_price, pnl = 0, None, 0  # Initialize trading position and PnL

def process_data(df, current_price, signal):
    global position, entry_price, pnl
    meets_threshold = False

    # Calculate threshold only if there's a position and entry price
    if entry_price is not None:
        price_diff = (current_price - entry_price) if position == 1 else (entry_price - current_price)
        meets_threshold = price_diff / entry_price >= profit_threshold

    if signal == 'Buy' and position == 0 and meets_threshold:
        position, entry_price = 1, current_price
    elif signal == 'Sell' and position == 1 and meets_threshold:
        pnl += (current_price - entry_price) * quantity
        position, entry_price = 0, None
    elif signal == 'Sell' and position == 0 and meets_threshold:
        position, entry_price = -1, current_price
    elif signal == 'Buy' and position == -1 and meets_threshold:
        pnl += (entry_price - current_price) * quantity
        position, entry_price = 0, None

    df.loc[df.index[-1], 'PnL'] = pnl
    return df.dropna(subset=['Signal'])


# def process_data(message):
#     global live_df
   
#     timeperiod, position, entry_price, pnl = 15, 0, None, 0
    
#     if len(df) < timeperiod+1:
#         return  

#     for i in range(timeperiod, len(df)):
#         df_subset = df.iloc[i - timeperiod:i + 1]
        
#         signal, current_price = df_subset['Signal'].iloc[-1], df_subset['Close'].iloc[-1]
        
#         #logging.debug('checking to see if there is a signal')
#         # Check if there's a signal and calculate potential profit/loss
#         if signal == 'Buy' or signal =='Sell':                
#             # Set price difference and threshold condition only if entry_price is defined
#             if entry_price is not None:
#                 #print("entry_price is not none")
#                 logging.debug('entry_price is not none')
                
#                 price_diff = (current_price - entry_price) if position == 1 else (entry_price - current_price)
#                 meets_threshold = price_diff / entry_price >= profit_threshold
#                 print("price_diff_hold:",price_diff / entry_price)
#             else:
#                 #print("entry_price is  none")
#                 logging.debug('entry_price is none')
#                 meets_threshold = True  # First buy or short action doesn't need a threshold check

#             # Execute buy/sell logic based on threshold check
#             if signal == 'Buy' and position == 0 and meets_threshold:
#                 position, entry_price = 1, current_price
#             elif signal == 'Sell' and position == 1 and meets_threshold:
#                 pnl += (current_price - entry_price) * quantity
#                 position, entry_price = 0, None  # Reset entry price after selling
#             elif signal == 'Sell' and position == 0 and meets_threshold:
#                 position, entry_price = -1, current_price
#             elif signal == 'Buy' and position == -1 and meets_threshold:
#                 pnl += (entry_price - current_price) * quantity
#                 position, entry_price = 0, None  # Reset entry price after covering

#         # Update PnL and Signal in the DataFrame
#         df.loc[df_subset.index[-1], 'PnL'], df.loc[df_subset.index[-1], 'Signal'] = pnl, signal
#         #timeperiod = min(timeperiod + 1, max_timeperiod)
#     #df.to_csv('backtest_rsi_bollinger_results.csv', index=True)  # Set index=False if you don’t need the index column in the CSV

#     return df.dropna(subset=['Signal'])

# def beginCollectiveTABasedStrategy(client,symbol_map):
#     while True:
#         if df.empty:
#             continue

#         print(live_df.tail())  # Print the latest rows for verification    
#         current_feed = get_live_feed(client,symbols_map)
       

#         # Append data to DataFrame
#         new_row = {"Date": current_feed['date'], "Close": close_price, "Signal": signal, "PnL": pnl}
#         df = pd.concat([live_df, pd.DataFrame([new_row])], ignore_index=True)

#         df = add_intraday_indicators(data)
#         df = generate_intraday_signals(df)
        
        
        
#         process_data(df)
#         if df['Signal'].iloc[-1] == 'Buy':
#             place_order(stock + '.NS', "BUY", 1)
#         elif df['Signal'].iloc[-1] == 'Sell':
#             place_order(stock + '.NS', "SELL", 1)

#         time.sleep(5)





def beginCollectiveTABasedStrategy(client, symbol_map):
    df = pd.DataFrame(columns=["Date", "Close", "Signal", "PnL"])
    
    while True:
        # Fetch current live feed data
        current_feed = get_live_feed(client, symbol_map)  # Ensure this function is defined
        close_price = float(current_feed["data"]["close"])
        date = datetime.now()
        
        # Append new row to the DataFrame
        new_row = {"Date": date, "Close": close_price, "Signal": None, "PnL": pnl}
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

        # Recalculate indicators for the latest period
        if len(df) >= max_timeperiod:
            df = add_intraday_indicators(df.iloc[-max_timeperiod:])  # Add indicators to the latest window
            df = generate_intraday_signals(df)  # Add signals
            
            # Process the latest data for trade decisions
            signal = df['Signal'].iloc[-1]
            df = process_data(df, close_price, signal)

            # Execute trade if signal exists
            if signal == 'Buy':
                place_order("BUY", 1)  # Replace with actual order logic
            elif signal == 'Sell':
                place_order("SELL", 1)  # Replace with actual order logic

        # Throttle for the next update
        time.sleep(5)


print("Executing RSI Bollinger Strategy")

try:
    feedToken=''
    client = SmartConnect(api_key=creds['api_key'])
    if not os.path.exists(jwtTokenFile):
        data = client.generateSession(creds['client_id'], creds['password'], creds['totp_key'])
        refreshToken = data['data']['refreshToken']
        response = client.generateToken(refreshToken)
        jwtToken, feedToken = response['data']['jwtToken'], response['data']['feedToken']
        encrypt_and_persist_token(jwtToken, jwtTokenFile, keyfile)
        encrypt_and_persist_token(feedToken, feedTokenFile, keyfile)
        encrypt_and_persist_token(refreshToken, refreshTokenFile, keyfile)
    else:
        print("decrypting token")
        jwtToken = read_and_decrypt_token(keyfile, jwtTokenFile)
        feedToken = read_and_decrypt_token(keyfile, feedTokenFile)
        client.setAccessToken(jwtToken)
        client.setFeedToken(feedToken)
    
    logging.info("Logged in successfully")
    print("Logged in successfully")
    # Run the WebSocket connection
    #url = f"wss://smartapisocket.angelone.in/smart-stream?clientCode={creds['client_id']}&feedToken={feedToken}&apiKey={creds['api_key']}"
    
    symbols_map = download_and_map_symbols()
    token=symbols_map[symbol]
    
    #live run
    beginCollectiveTABasedStrategy(client, symbols_map)

    #websocket doesn't binary parsing fails
    #init_websocket(symbol,feedToken)


    #backtest strategy
    #backtest_results = backtest_intraday_strategy_with_profit_threshold(symbol+'.NS', '2024-10-28', interval='1m', quantity=10)
    #logging.info(backtest_results)
except Exception as e:
    logging.error(f"Login error: {e}")
    exit()
