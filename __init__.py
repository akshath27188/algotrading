import logging

#Trading hours
start_time = "01:00"
end_time = "15:30"

#generated keyfile path
keyfile="key.bin"
jwtTokenFile = "./jwtToken"
feedTokenFile = "./feedToken"
refreshTokenFile = "./refreshToken"

# Define trading parameters
symbol = "CASTROLIND-EQ"
initial_capital = 400000  # Starting capital (Rs)
initial_position_size = 100  # Number of shares to buy initially
buy_increment_pct = 0.03 / 100  # Buy more after a 0.1% price drop
profit_target_pct = 0.5 / 100  # Sell when 0.7% profit is achieved
stop_loss_pct = 0.25 / 100  # Stop loss at 0.35% price drop
entry_price = 1035
LIVE_FEED_INTERVAL=5 #in seconds
symbols_map=None


# Angel One SmartAPI credentials
creds = {
    "client_id": "A227074",
    "password": "7882",
    "api_key": "DdeNeHJ4",
    "totp_key": "181670"  # TOTP key for 2FA
}

# Configure the logging
# logging.basicConfig(
#     filename='app-'+symbol+'.log',  # Name of the log file
#     level=logging.DEBUG,  # Minimum level of messages to log
#     format='%(asctime)s - %(levelname)s - %(message)s'  # Format of the log messages
# )





