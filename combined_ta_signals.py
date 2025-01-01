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
import sys
from trade_utils import *
from __init__ import *
from angel_websocket import *
import traceback
import argparse
import signal
# Configure the logging
# logging.basicConfig(
#     filename='app-intraday.log',
#     level=logging.DEBUG,
#     format='%(asctime)s - %(levelname)s - %(message)s'
# )

#symbol = 'GANESHHOUC-EQ'
holdings = ['ACI', 'GANESHHOUC', 'GIPCL', 'INDIANHUME', 'KARURVYSYA', 
            'LTFOODS', 'MAHSEAMLES', 'MANINDS', 'MANINFRA', 'MOIL', 
            'MOTHERSON', 'NATIONALUM', 'NHPC', 'PARADEEP', 'PENIND', 
            'RECLTD', 'RITES', 'RTNPOWER', 'SBIN', 'SBINEQWETF', 
            'SOUTHBANK', 'UJJIVANSFB', 'YATHARTH', 'YESBANK', 'INDRAMEDCO']



# Global parameters
live_df = []
profit_threshold = 0.002  # difference of entry and current price divided by current price not the same as profit percentage 
quantity_per_trade = 1  # Quantity to trade per order - for live trade 
quantity = 1  # Quantity to trade - for backtest data  
timeperiod = 15  # Indicator period
position, profit = 0, 0  # Initialize trading position and PnL
backup_live_file_path = "./backup_live_file_path"

# The first argument is the script name, and the subsequent arguments are user inputs
if len(sys.argv) > 3:
    global symbol,entry_price
    print(f"Argument received: {sys.argv[1]}")
    symbol = sys.argv[1]    
    quantity_per_trade = int(sys.argv[2])
    profit_threshold = float(sys.argv[3])
    if len(sys.argv) == 5 :
        entry_price = sys.argv[4] #optional
    else:
        entry_price = 0         
else:
    print("No argument provided! \n expected - python3 combined_ta_signals.py <symbol> <quantity_per_trade> <profit_threshold> <entry_price(optional)>")
    exit(1)

# Configure the logging
logging.basicConfig(
    filename='app-'+symbol+'.log',  # Name of the log file
    level=logging.DEBUG,  # Minimum level of messages to log
    format='%(asctime)s - %(levelname)s - %(message)s'  # Format of the log messages
)

logging.debug(f"symbol - {symbol}, quantity_per_trade - {quantity_per_trade}, profit_threshold - {profit_threshold}")
#highest rolling window of the 3 indicators , will also be used to as the timeperiod to process data 
max_timeperiod=20

#rsi,mcad indicator timeperiod
rsi_timeperiod=7
mfastperiod=6
mslowperiod=19
msignalperiod=5




# Initial capital and trading parameters
#initial_capital = 200000  # Example initial capital in rupees
available_capital = initial_capital
max_positions = 10  # Maximum number of concurrent positions
positions = []  # List to track open positions



def get_stock_data(ticker, period='1d', interval='5m'):
    try:
        stock_data = yf.download(ticker, period=period, interval=interval)
        if stock_data.empty:
            raise ValueError(f"No data returned for {ticker}")
        stock_data.index.name = 'Date'
        return stock_data
    except Exception as e:
        stack_trace = traceback.format_exc()
        #print("Stack trace as a string:")
        print(stack_trace)
        logging.debug(f'STACKTRACE-{stack_trace}')
        logging.error(f"Error downloading data for {ticker}: {e}")
        return pd.DataFrame()

def add_intraday_indicators(df,backtest):
    column_to_use = 'Close' if backtest else 'Ltp' 
    df['RSI'] = ta.RSI(df[column_to_use], timeperiod=rsi_timeperiod)
    df['Upper_BB'], df['Middle_BB'], df['Lower_BB'] = ta.BBANDS(df[column_to_use], timeperiod=max_timeperiod)
    df['MACD'], df['MACD_signal'], df['MACD_hist'] = ta.MACD(df[column_to_use], fastperiod=mfastperiod, slowperiod=mslowperiod, signalperiod=msignalperiod)
    return df

def generate_intraday_signals(df,backtest):
    column_to_use = 'Close' if backtest else 'Ltp'
    df['Signal'] = None
    for i in range(1, len(df)):
        # Skip if any required values are NaN
        if (np.isnan(df['RSI'].iloc[i]) or
                np.isnan(df[column_to_use].iloc[i]) or
                np.isnan(df['Upper_BB'].iloc[i]) or
                np.isnan(df['Lower_BB'].iloc[i]) or
                np.isnan(df['MACD'].iloc[i]) or
                np.isnan(df['MACD_signal'].iloc[i])):
            continue

        # Define parameters for oversold/overbought conditions
        rsi_oversold = 25  # Adjusted oversold threshold
        rsi_overbought = 75  # Adjusted overbought threshold
        rsi_bullish = 50
        rsi_bearish = 50

        # Define conditions for signals
        #TODO test with tolerance 
        is_oversold_bounce = df['RSI'].iloc[i] < rsi_oversold #and 
                            #   df[column_to_use].iloc[i] > df['Lower_BB'].iloc[i] and 
                            #   df[column_to_use].iloc[i-1] <= df['Lower_BB'].iloc[i-1])
        
        is_overbought_bounce = df['RSI'].iloc[i] > rsi_overbought #and 
                                # df[column_to_use].iloc[i] < df['Upper_BB'].iloc[i] and 
                                # df[column_to_use].iloc[i-1] >= df['Upper_BB'].iloc[i-1])

        # Define breakout conditions
        # is_bullish_breakout = (df['Ltp'].iloc[i] > df['Upper_BB'].iloc[i] and 
        #                         df['RSI'].iloc[i] > rsi_bullish and 
        #                         df['MACD'].iloc[i] > df['MACD_signal'].iloc[i])
        
        # is_bearish_breakout = (df['Ltp'].iloc[i] < df['Lower_BB'].iloc[i] and 
        #                         df['RSI'].iloc[i] < rsi_bearish and 
        #                         df['MACD'].iloc[i] < df['MACD_signal'].iloc[i])                        
        

        is_macd_buy = (df['MACD'].iloc[i] > df['MACD_signal'].iloc[i] and 
                       df['MACD'].iloc[i-1] <= df['MACD_signal'].iloc[i-1])
        
        is_macd_sell = (df['MACD'].iloc[i] < df['MACD_signal'].iloc[i] and 
                        df['MACD'].iloc[i-1] >= df['MACD_signal'].iloc[i-1])

        # Combine conditions to generate signals
        if is_oversold_bounce:# or is_macd_buy:
            df.loc[df.index[i], 'Signal'] = 'Buy'
        elif is_overbought_bounce:# or is_macd_sell:
            df.loc[df.index[i], 'Signal'] = 'Sell'
        # elif is_bullish_breakout:
        #     df.loc[df.index[i], 'Signal'] = 'Double-Buy'
        # elif is_bearish_breakout:
        #     df.loc[df.index[i], 'Signal'] = 'Double-Sell'      

    return df

def execute_intraday_strategy(ticker,backtest):
    column_to_use = 'Close' if backtest else 'Ltp'
    df = get_stock_data(ticker, period='1d', interval='5m')
    if df.empty:
        logging.warning(f"Skipping {ticker} due to missing data or error")
        return df

    df = add_intraday_indicators(df,column_to_use)
    df = df.dropna(subset=['RSI', 'Upper_BB', 'Lower_BB', 'MACD', 'MACD_signal', 'MACD_hist'])
    df = generate_intraday_signals(df,backtest)
    df = df.dropna(subset=['Signal']).reset_index()
    return df[['Date', column_to_use, 'RSI', 'Upper_BB', 'Lower_BB', 'MACD', 'MACD_signal', 'MACD_hist', 'Signal']]

def backtest_intraday_strategy(ticker, date, interval='1m', max_timeperiod=15, quantity=1):
    try:
        start_date = pd.to_datetime(date)
        end_date = start_date + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        data = yf.download(ticker, start=start_date, end=end_date, interval=interval)
        print(data)
        if data.empty:
            logging.warning(f"No data found for {ticker} on {date}")
            return pd.DataFrame()

        df = add_intraday_indicators(data,True)
        df = generate_intraday_signals(df,True)  # Generate signals once at the start
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
        stack_trace = traceback.format_exc()
        #print("Stack trace as a string:")
        print(stack_trace)
        logging.debug(f'STACKTRACE-{stack_trace}')
        return pd.DataFrame()


def backtest_intraday_strategy_with_profit_threshold_cumulative_indicators(ticker, date, interval='1m', max_timeperiod=60, quantity=1, profit_threshold=0.002):
    try:
        start_date = pd.to_datetime(date)
        end_date = start_date + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        data = yf.download(ticker, start=start_date, end=end_date, interval=interval)
        print('data: ---',data)
        if data.empty:
            logging.warning(f"No data found for {ticker} on {date}")
            return pd.DataFrame()

        df = add_intraday_indicators(data,True)
        df = generate_intraday_signals(df,True)
        timeperiod, position, entry_price, pnl = 15, 0, 0, 0
        
        for i in range(timeperiod, len(df)):
            df_subset = df.iloc[i - timeperiod:i + 1]
            
            signal, current_price = df_subset['Signal'].iloc[-1], df_subset['Close'].iloc[-1]
            #logging.debug(f"meets_threshold:{meets_threshold} ,  price_diff - {price_diff}, entry_price - {entry_price}, current_price - {current_price}, actual profit threshold - {profit_threshold}, quantity - {quantity}")
            #logging.debug('checking to see if there is a signal')
            # Check if there's a signal and calculate potential profit/loss
            if signal == 'Buy' or signal =='Sell':                
                # Set price difference and threshold condition only if entry_price is defined
                if entry_price > 0:
                    #print("entry_price is not none")
                    logging.debug('entry_price is not none')
                    
                    price_diff = (current_price - entry_price) if position == 1 else (entry_price - current_price)
                    meets_threshold = float(price_diff / entry_price) >= float(profit_threshold)
                    logging.debug(f"meets_threshold:{meets_threshold} ,  price_diff - {price_diff}, entry_price - {entry_price}, current_price - {current_price}, actual profit threshold - {profit_threshold}, quantity - {quantity}")
                else:
                    #print("entry_price is  none")
                    logging.debug('entry_price is none')
                    meets_threshold = True  # First buy or short action doesn't need a threshold check

                # Execute buy/sell logic based on threshold check
                if signal == 'Buy' and position == 0 and meets_threshold:
                    position, entry_price = 1, current_price
                elif signal == 'Sell' and position == 1 and meets_threshold:
                    pnl += (current_price - entry_price) * quantity
                    position, entry_price = 0, 0  # Reset entry price after selling
                elif signal == 'Sell' and position == 0 and meets_threshold:
                    position, entry_price = -1, current_price
                elif signal == 'Buy' and position == -1 and meets_threshold:
                    pnl += (entry_price - current_price) * quantity
                    position, entry_price = 0, 0  # Reset entry price after covering

            # Update PnL and Signal in the DataFrame
            df.loc[df_subset.index[-1], 'PnL'], df.loc[df_subset.index[-1], 'Signal'] = pnl, signal
            #timeperiod = min(timeperiod + 1, max_timeperiod)
        #df.to_csv('backtest_rsi_bollinger_results.csv', index=True)  # Set index=False if you don’t need the index column in the CSV
    
        return df.dropna(subset=['Signal'])
    except Exception as e:
        logging.error(f"Backtesting error: {e}")
        return pd.DataFrame()


def backtest_intraday_strategy_with_profit_threshold(ticker, date, interval='1m', max_timeperiod=60, quantity=1, profit_threshold=0.06):
    try:
        start_date = pd.to_datetime(date)
        end_date = start_date + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        print(f"start_date - {start_date} , end_date - {end_date}")
        data = yf.download(ticker, start=start_date, end=end_date, interval=interval)
        print('data: ---',data)
        if data.empty:
            logging.warning(f"No data found for {ticker} on {date}")
            return pd.DataFrame()

        # df = add_intraday_indicators(data,True)
        # df = generate_intraday_signals(df,True)
        timeperiod, position, entry_price, pnl = 15, 0, 0, 0
        #df['Pnl'] = 0
        constructive_df = pd.DataFrame(columns=["Date", "Close", "Signal", "PnL"])
        for i in range(timeperiod, len(data)):
            #logging.debug(current_feed)
            ltp_price = float( data['Close'].iloc[i])
            date = datetime.now()
            
            
            # Append new row to the DataFrame
            new_row = {"Date": date, "Close": ltp_price, "Signal": None, "PnL": pnl}
            constructive_df = pd.concat([constructive_df, pd.DataFrame([new_row])], ignore_index=True)
            pd.set_option('display.max_columns', None)
            print('Length of df - ',len(constructive_df))
            # Recalculate indicators for the latest period
            if len(constructive_df) >= max_window:
                wdf = add_intraday_indicators(constructive_df.iloc[-max_window:] , True)  # Add indicators to the latest window
                print('Length of df after indicators- ',len(wdf))
                wdf = generate_intraday_signals(wdf,True)  # Add signals
                print('Length of df after signals- ',len(wdf))
                
                # Process the latest data for trade decisions
                signal = wdf['Signal'].iloc[-1]
                print('signal-',signal)
                logging.info(wdf)
                processed_df = process_data(wdf,True) #, ltp_price, signal)
                print('Length of df after process_data( shows value only if there is a signal generated)- ',len(processed_df))    

           
            #signal, current_price = wdf['Signal'].iloc[-1], wdf['Close'].iloc[-1]
            
            # #logging.debug('checking to see if there is a signal')
            # # Check if there's a signal and calculate potential profit/loss
            #if signal == 'Buy' or signal =='Sell':                
            #     # Set price difference and threshold condition only if entry_price is defined
            #     if entry_price > 0:
            #         #print("entry_price is not none")
            #         logging.debug('entry_price is not none')
                    
            #         price_diff = (current_price - entry_price) if position == 1 else (entry_price - current_price)
            #         meets_threshold = float( price_diff / entry_price ) >= float(profit_threshold)
            #         print("price_diff_hold:",price_diff / entry_price)
            #         logging.debug(f"meets_threshold:{meets_threshold} ,  price_diff - {price_diff}, entry_price - {entry_price}, current_price - {current_price}, actual profit threshold - {profit_threshold}, quantity - {quantity}")
            #     else:
            #         #print("entry_price is  none")
            #         logging.debug('entry_price is none')
            #         meets_threshold = True  # First buy or short action doesn't need a threshold check

            #     # Execute buy/sell logic based on threshold check
            #     if signal == 'Buy' and position == 0 and meets_threshold:
            #         position, entry_price = 1, current_price
            #     elif signal == 'Sell' and position == 1 and meets_threshold:
            #         pnl += (current_price - entry_price) * quantity
            #         position, entry_price = 0, 0  # Reset entry price after selling
            #     elif signal == 'Sell' and position == 0 and meets_threshold:
            #         position, entry_price = -1, current_price
            #     elif signal == 'Buy' and position == -1 and meets_threshold:
            #         pnl += (entry_price - current_price) * quantity
            #         position, entry_price = 0, 0  # Reset entry price after covering

            # # Update PnL and Signal in the DataFrame
            # df.loc[df_subset.index[-1], 'PnL'], df.loc[df_subset.index[-1], 'Signal'] = pnl, signal
                # process_data(wdf,True)
                # timeperiod = min(timeperiod + 1, max_timeperiod)
        #df.to_csv('backtest_rsi_bollinger_results.csv', index=True)  # Set index=False if you don’t need the index column in the CSV
    
        return df.dropna(subset=['Signal'])
    except Exception as e:
        stack_trace = traceback.format_exc()
        #print("Stack trace as a string:")
        print(stack_trace)
        logging.debug(f'STACKTRACE-{stack_trace}')
        logging.error(f"Backtesting error: {e}")
        return pd.DataFrame()



positions = []
def execute_trade(pdf,signal, current_price,backtest,symbol,token,client):
    global available_capital, quantity_per_trade,profit,entry_price,pos_price
    
    

    # # Calculate the cost of one trade
    # if signal == 'Double-Buy' or signal == 'Double-Sell':
    #     trade_cost = 2*quantity_per_trade * current_price
    # else:
    trade_cost = quantity_per_trade * current_price
    # if entry_price is not None:       
    #         print("entry price is not none ")
    #         logging.debug('entry_price is not none')
    #         price_diff = (current_price - entry_price) if is_position_sell == 'Sell' else (entry_price - current_price)
    #         meets_threshold = price_diff / entry_price >= profit_threshold
    # else:
    #         print("entry_price is  none")
    #         logging.debug('entry_price is none')
    #         meets_threshold = True  # First buy or short action doesn't need a threshold check    

    #logging.debug(f"execute trade func , current_price ---  {current_price}, Remaining Capital: {available_capital}, entry-price - {entry_price}, meets threshold- {meets_threshold}")
    #spdf = pdf.copy()
    
    #pdf.dropna(['Signal'])
    ##breakout scenario
    # if signal =='Double-Buy' and available_capital >= trade_cost:
    #     if len(positions)>0 and any(pos['type'] == 'Sell' for pos in positions) :
    #         ##square off pending therefore stop loss and buy again due to breakout
    #         #this should cover the existing position and add existing trade_cost 
    #         # value  of cover and trade cost for more buy will be almost same  so the capital will be the same, 
    #         # need to factor in profits/losses later
    #         #available_capital -= trade_cost
    #         for pos in positions:
    #             positions.append({'type': 'Buy', 'price': current_price, 'quantity': quantity_per_trade})
    #             print(f"Executed Double Buy at {current_price}, Remaining Capital: {available_capital}")
    #             logging.debug(f"Executed Double Buy(cover short sell position and buy moder of same qty) at {current_price}, position price:{pos['price']}, Remaining Capital: {available_capital}")
    #             entry_price = current_price
    #             profit += (pos['price'] - current_price) * pos['quantity']
    #             available_capital += profit
    #             positions.remove(pos)
    #     else:
    #        # Execute a buy if there is enough capital
    #         available_capital -= trade_cost
    #         positions.append({'type': 'Buy', 'price': current_price, 'quantity': quantity_per_trade})
    #         print(f"Executed Buy from breakout signal at {current_price}, Remaining Capital: {available_capital}")
    #         logging.debug(f"Executed Buy from breakout singal at {current_price}, Remaining Capital: {available_capital}")
    #     entry_price = current_price 


    # elif signal =='Double-Sell' and available_capital >= trade_cost:
    #     if len(positions)>0 and any(pos['type'] == 'Buy' for pos in positions) :
    #         ##square off pending for stop loss and buy again due to breakout
    #         ## so capital should be almost same
    #         #available_capital -= trade_cost
    #         for pos in positions:
    #             positions.append({'type': 'Sell', 'price': current_price, 'quantity': quantity_per_trade})
    #             print(f"Executed Double Sell at {current_price}, Remaining Capital: {available_capital}, position price:{pos['price']}")
    #             logging.debug(f"Executed Double Sell(cover buy position and short sell same qty) at {current_price}, Remaining Capital: {available_capital}")
    #             entry_price = current_price
    #             profit += (current_price - pos['price']) * pos['quantity']
    #             available_capital += profit
    #             positions.remove(pos)
    #     else:
    #          # Execute a short sell if there is enough capital
    #         available_capital -= trade_cost
    #         positions.append({'type': 'Sell', 'price': current_price, 'quantity': quantity_per_trade})
    #         print(f"Executed Short Sell from breakout signal at {current_price}, Remaining Capital: {available_capital}")
    #         logging.debug(f"Executed Sell from breakout singal at {current_price}, Remaining Capital: {available_capital}")
        

    #logging.debug(f"meets_threshold:{meets_threshold} ,  price_diff - {price_diff}, entry_price - {entry_price}, current_price - {current_price}, actual profit threshold - {profit_threshold}, quantity - {quantity}")
    position_length=len(positions)
    if position_length >= 1:
        positions[0]['diff_threshold'] = abs(positions[0]['price'] - current_price) 
        logging.debug(f"signal:{signal}, available_capital : {available_capital}, trade_cost:{trade_cost}, position length:{position_length}, positions - {positions}, diff threshold - {positions[0]['diff_threshold']}") 
    
    
    logging.debug(f"signal:{signal}, available_capital : {available_capital}, trade_cost:{trade_cost}, position length:{position_length}")
    if signal == 'Buy' and available_capital >= trade_cost and len(positions) == 0:
        # Execute a buy if there is enough capital       
        orderDetails = placeOrderFullResponse(client,'BUY', quantity_per_trade, current_price,symbol,token)
        orderStatusDetails = get_status_details(client,orderDetails['data']['uniqueorderid'],1)
        orderStatus = orderStatusDetails['data']['orderstatus']
        logging.debug(f'order status - {orderStatusDetails}')
        if orderDetails and orderStatus =='complete' :
            available_capital -= trade_cost
            positions.append({'type': 'Buy', 'price': current_price, 'quantity': quantity_per_trade})
            print(f"Executed Buy at {current_price}, Remaining Capital: {available_capital}")
            logging.debug(f"Executed Buy at {current_price}, Remaining Capital: {available_capital}")
            entry_price = current_price
        if orderStatus == 'open':
            cancel_order(client, orderDetails['data']['orderid'],1)        
        

    elif signal == 'Sell' and any(pos['type'] == 'Buy' for pos in positions) :
        # Check for existing buy positions to sell
        for pos in positions:
            if pos['type'] == 'Buy':
                price_diff = float(current_price - pos['price'])
                diff_threshold = float(price_diff / pos['price'])
                meets_threshold = float(price_diff / pos['price']) >= profit_threshold
                logging.debug(f"diff_threshold - {diff_threshold}, profit_threshold - {profit_threshold}")

                if meets_threshold:
                    orderDetails = placeOrderFullResponse(client,'SELL', quantity_per_trade, current_price,symbol,token)
                    orderStatusDetails = get_status_details(client,orderDetails['data']['uniqueorderid'],1)
                    orderStatus = orderStatusDetails['data']['orderstatus']
                    logging.debug(f'order status - {orderStatusDetails}')
                    if orderDetails and orderStatus=='complete' :                        
                        profit += (current_price - pos['price']) * pos['quantity']
                        available_capital += trade_cost + profit
                        positions.remove(pos)
                        print(f"Executed Sell at {current_price}, entry-price: {pos['price']},  Profit: {profit}, Remaining Capital: {available_capital}")
                        logging.debug(f"Executed Sell at {current_price}, entry-price: {pos['price']}, Profit: {profit}, Remaining Capital: {available_capital}")
                        break
                    if orderStatus == 'open':
                        cancel_order(client, orderDetails['data']['orderid'],1)    


    elif signal == 'Sell' and available_capital >= trade_cost and len(positions) == 0:
        # Execute a short sell if there is enough capital
        orderDetails = placeOrderFullResponse(client,'SELL', quantity_per_trade, current_price,symbol,token)
        orderStatusDetails = get_status_details(client,orderDetails['data']['uniqueorderid'],1)
        orderStatus = orderStatusDetails['data']['orderstatus']
        logging.debug(f'order status - {orderStatusDetails}')
        if orderDetails and orderStatus=='complete' :   
            available_capital -= trade_cost
            entry_price = current_price
            positions.append({'type': 'Sell', 'price': current_price, 'quantity': quantity_per_trade})
            print(f"Executed Short Sell at {current_price}, Remaining Capital: {available_capital}")
            logging.debug(f"Executed Short Sell at {current_price}, Remaining Capital: {available_capital}")
        if orderStatus == 'open':
            cancel_order(client, orderDetails['data']['orderid'],1)        
        

    elif signal == 'Buy' and any(pos['type'] == 'Sell' for pos in positions):
        # Check for existing short positions to cover
        for pos in positions:
            if pos['type'] == 'Sell':
                price_diff = float(pos['price'] - current_price)
                diff_threshold = float(price_diff / pos['price'])
                meets_threshold = float(price_diff / pos['price']) >= profit_threshold
                logging.debug(f"diff_threshold - {diff_threshold}, profit_threshold - {profit_threshold}")
                
                if meets_threshold:
                    orderDetails = placeOrderFullResponse(client,'BUY', quantity_per_trade, current_price,symbol,token)
                    orderStatusDetails = get_status_details(client,orderDetails['data']['uniqueorderid'])
                    orderStatus = orderStatusDetails['data']['orderstatus']
                    logging.debug(f'order status - {orderStatusDetails}')
                    if orderDetails and orderStatus=='complete' :   
                        profit += (pos['price'] - current_price) * pos['quantity']
                        available_capital += trade_cost + profit
                        positions.remove(pos)
                        #entry_price=None
                        print(f"Executed Buy to Cover at {current_price}, entry-price: {pos['price']}, Profit: {profit}, Remaining Capital: {available_capital}")
                        logging.debug(f"Executed Buy to Cover at {current_price}, entry-price: {pos['price']}, Profit: {profit}, Remaining Capital: {available_capital}")
                        break
                    if orderStatus == 'open':
                        cancel_order(client, orderDetails['data']['orderid'],1)    
    
    #logging.debug(f"value after setting entry price  - {entry_price}")
    pdf.loc[pdf.index[-1], 'PnL'] = profit
    #pdf.set_option('display.max_columns', None)
    return pdf   #.dropna(subset=['Signal'])           

def process_data(pdf,backtest,symbol,token,client):
    column_to_use = 'Close' if backtest else 'Ltp' 
    signal = pdf['Signal'].iloc[-1]
    current_price = pdf[column_to_use].iloc[-1]
    
    #print('processing data')
    #logging.debug('processing data'),
    #Execute trade based on the signal and update available capital and positions
    df = execute_trade(pdf,signal, current_price,backtest,symbol,token,client)
    return df
    # global position, entry_price, pnl
    # meets_threshold = False
    # logging.debug(f"signal - {str(signal)}")

    # if signal == 'Buy' or signal =='Sell':
    #     logging.debug("There is a buy/sell signal") 
    #     print("There is a buy/sell signal")
    # # Calculate threshold only if there's a position and entry price
    #     logging.debug(f"before processing  --- meets threshold:{str(meets_threshold)} , entry price:{str(entry_price)} , signal: {str(signal)}, current_price:{str(current_price)} , pnl - {str(pnl)}, position: {str(position)}")
    #     print("meets threshold:",meets_threshold,"entry price:",entry_price," signal - ",signal," current_price:",current_price)
    #     if entry_price is not None:       
    #         print("entry price is not none ")
    #         logging.debug('entry_price is none')
    #         price_diff = (current_price - entry_price) if position == 1 else (entry_price - current_price)
    #         meets_threshold = price_diff / entry_price >= profit_threshold
    #     else:
    #         print("entry_price is  none")
    #         logging.debug('entry_price is none')
    #         meets_threshold = True  # First buy or short action doesn't need a threshold check    

    #     if signal == 'Buy' and position == 0 and meets_threshold:
    #         position, entry_price = 1, current_price
    #     elif signal == 'Sell' and position == 1 and meets_threshold:
    #         pnl += (current_price - entry_price) * quantity
    #         position, entry_price = 0, None
    #     elif signal == 'Sell' and position == 0 and meets_threshold:
    #         position, entry_price = -1, current_price
    #     elif signal == 'Buy' and position == -1 and meets_threshold:
    #         pnl += (entry_price - current_price) * quantity
    #         position, entry_price = 0, None

    # logging.debug(f"after processing   --- position: {str(position)}, entry_price: {str(entry_price)}, pnl: {str(pnl)}")

    # pdf.loc[pdf.index[-1], 'PnL'] = pnl
    # return pdf   #.dropna(subset=['Signal'])


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

#         time.sleep(60)



max_window=40
def beginCollectiveTABasedStrategy(client, symbol_map,symbol,token,backtest,df):
    
    #pd.set_option('display.max_columns', None)
    while True:
        # Fetch current live feed data
        current_feed = get_live_feed(client, symbol_map,symbol)  # Ensure this function is defined
        if current_feed == None or not current_feed['data']:
            time.sleep(1)
            continue
            

        ltp = current_feed["data"]["ltp"]    
        logging.debug(f"ltp value : {ltp}")        
        ltp_price = float(current_feed["data"]["ltp"])
        date = datetime.now()
        
        # Append new row to the DataFrame
        new_row = {"Date": date, "Ltp": ltp_price, "Signal": None, "PnL": pnl}
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        pd.set_option('display.max_columns', None)
        print('Length of df - ',len(df))
        # Recalculate indicators for the latest period
        if len(df) >= max_window:
            wdf = add_intraday_indicators(df.iloc[-max_window:] , False)  # Add indicators to the latest window
            print('Length of df after indicators- ',len(wdf))
            wdf = generate_intraday_signals(wdf,False)  # Add signals
            print('Length of df after signals- ',len(wdf))
            
            # Process the latest data for trade decisions
            signal = wdf['Signal'].iloc[-1]
            print('signal-',signal)
            logging.info(wdf)

            #check for stoploss
            if len(positions)>=1:
                diff_threshold = abs(positions[0]['price'] - ltp_price) / positions[0]['price'] 
                if positions[0]['type'] =='Buy' and ltp_price < positions[0]['price'] and diff_threshold >= profit_threshold/2:
                       #sell
                       orderDetails = placeOrderFullResponse(client,'SELL', positions[0]['quantity'], ltp_price,symbol,token)
                       positions.remove(positions[0])
                       logging.debug(f'stop loss order details- {orderDetails}')
                if positions[0]['type'] == 'Sell' and ltp_price > positions[0]['price'] and diff_threshold >= profit_threshold/2:
                        #buy 
                       orderDetails = placeOrderFullResponse(client,'BUY', positions[0]['quantity'], ltp_price,symbol,token)
                       positions.remove(positions[0])
                       logging.debug(f'stop loss order details- {orderDetails}')
            #positions[0]['diff_threshold'] = abs(positions[0]['price'] - current_price) 
            processed_df = process_data(wdf,False,symbol,token,client) #, ltp_price, signal)
            print('Length of df after process_data( shows value only if there is a signal generated)- ',len(processed_df))
            #wdf.dropna(subset=['RSI', 'Upper_BB', 'Lower_BB'])
            # # Execute trade if signal exists
            # if signal == 'Buy':
            #     logging.info("placing buy order")
            #     #place_order("BUY", 1)  # Replace with actual order logic
            # elif signal == 'Sell':
            #     logging.info("placing sell order")
            #     #place_order("SELL", 1)  # Replace with actual order logic

        # Throttle for the next update
        time.sleep(10)


def cleanup_and_exit(args):
    global df
    #if args.load_live_data_from_interrupt.upper() == 'Y':
    df.to_csv('backup_live_file_path.csv', index=True)

def handleInterrupts(args):
    global df
    # Attach signal handlers
    signal.signal(signal.SIGINT, cleanup_and_exit)  # For Ctrl+C
    signal.signal(signal.SIGTERM, cleanup_and_exit)  # For `kill` command
    if args.load_live_data_from_interrupt.upper() == 'Y':
        df = pd.read_csv(backup_live_file_path)        
    # Simulate long-running process
    print("Running process. Press Ctrl+C or send SIGTERM to terminate.")
    

print("Executing RSI Bollinger Strategy")
#otp authentication read from init file , generate token and persist to file for subsequent runs incase of interrupt
try:
    args = None
    feedToken=''
    client = SmartConnect(api_key=creds['api_key'])
    if not os.path.exists(jwtTokenFile):
        data = client.generateSession(creds['client_id'], creds['password'], creds['totp_key'])
        logging.debug(f'login response - {data}')
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
    
    
    #parse script arguments passed from sh file or commandline
    try:
        
        
        parser = argparse.ArgumentParser(description="Process trading arguments.")
        parser.add_argument("symbol", help="Stock symbol")
        parser.add_argument("quantity", type=int, help="Quantity to trade")
        parser.add_argument("tolerance", type=float, help="Tolerance level")
        parser.add_argument("--position_status", help="Existing positions (Y/N)", default="N")
        parser.add_argument("--order_type", help="Order type (Buy/Sell)", default=None)
        parser.add_argument("--price", type=float, help="Position price", default=0.0)
        parser.add_argument("--quantity_pos", type=int, help="Position quantity", default=0)
        parser.add_argument("--load_live_data_from_interrupt", help="Load live data after restarting from interrupt", default="N")
        args = parser.parse_args()
        handleInterrupts(args)
        positions = []
        print(type(args.position_status))  # Check if it is a string
        print(args.position_status.upper)  # Check if it is still the string method

        if args.position_status.upper() == "Y":
            pos = {
                "type": args.order_type,
                "price": args.price,
                "quantity": args.quantity_pos,
            }
            positions.append(pos)

        print(f"Your stock: {args.symbol}, Positions: {positions}")

       

    except Exception as e:
        stack_trace = traceback.format_exc()
        #print("Stack trace as a string:")
        print(stack_trace)
        print(f"Error: {e}")
        sys.exit(1)


    logging.info("Logged in successfully")
    print("Logged in successfully")
    # Run the WebSocket connection
    #url = f"wss://smartapisocket.angelone.in/smart-stream?clientCode={creds['client_id']}&feedToken={feedToken}&apiKey={creds['api_key']}"
    
    symbols_map = download_and_map_symbols()
    token=symbols_map[symbol]
    
    logging.debug(f"symbol passed as : {symbol} and token - {token}")

    
    #column_to_use = 'Close' if backtest else 'Ltp' 
    df = pd.DataFrame(columns=["Date", 'Ltp', "Signal", "PnL"])

    #live run
    
    beginCollectiveTABasedStrategy(client, symbols_map,symbol,token,False,df)

    #websocket doesn't binary parsing fails - not working
    #init_websocket(symbol,feedToken)


    #backtest strategy
    #rolling indicators added to window
    #backtest_results = backtest_intraday_strategy_with_profit_threshold(symbol+'.NS', '2024-11-26', interval='1m', quantity=quantity_per_trade, profit_threshold=profit_threshold)
    #indicators added cumulatively to the entire dataset 
    #backtest_results = backtest_intraday_strategy_with_profit_threshold_cumulative_indicators(symbol+'.NS', '2024-12-03', interval='1m', quantity=quantity_per_trade, profit_threshold=profit_threshold)
    #both the above should yield results as in same profit, but that would depend on what price the entry was made, this will vary for both
    logging.info(backtest_results)
    
except Exception as e:
    stack_trace = traceback.format_exc()
    #print("Stack trace as a string:")
    print(stack_trace)
    logging.error(f"Login error: {e}")
    logging.debug(f'STACKTRACE-{stack_trace}')
    exit()
