import MetaTrader5 as mt5
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Initialize the MT5 connection
def initialize_mt5():
    if not mt5.initialize():
        raise RuntimeError(f"MetaTrader5 initialization failed, error code: {mt5.last_error()}")

# Helper function to convert exposure to account currency, considering contract size and base/quote currency conversion
def convert_to_account_currency(symbol, volume, price, account_currency):
    initialize_mt5()
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        raise RuntimeError(f"Symbol {symbol} not found")

    base_currency = symbol_info.currency_base
    quote_currency = symbol_info.currency_profit
    contract_size = symbol_info.trade_contract_size

    # Exposure in base currency
    exposure_base = volume * price * contract_size

    # Convert base currency to account currency if needed
    if quote_currency == account_currency:
        return exposure_base

    # Try the direct pair for conversion
    conversion_pair = f"{quote_currency}{account_currency}"
    try:
        if mt5.symbol_info(conversion_pair):
            conversion_rate = mt5.symbol_info_tick(conversion_pair).bid
        else:
            conversion_rate = None
    except Exception:
        conversion_rate = None

    if conversion_rate is None:
        # Try the reverse pair if direct pair is unavailable
        reverse_conversion_pair = f"{account_currency}{quote_currency}"
        reverse_symbol_info = mt5.symbol_info(reverse_conversion_pair)
        if reverse_symbol_info:
            try:
                conversion_rate = 1 / mt5.symbol_info_tick(reverse_conversion_pair).ask
            except Exception:
                conversion_rate = None

    if conversion_rate is None:
        # Workaround: Invert the base and quote currencies for common inverted symbols
        inverted_pair = f"{account_currency}{quote_currency}"
        inverted_symbol_info = mt5.symbol_info(inverted_pair)
        if inverted_symbol_info:
            try:
                conversion_rate = 1 / mt5.symbol_info_tick(inverted_pair).ask
            except Exception:
                conversion_rate = None

    if conversion_rate is None:
        raise RuntimeError(f"Cannot find conversion rate for {quote_currency} to {account_currency}")

    return exposure_base * conversion_rate

# Function to get currently open positions and their weight as a percentage of balance
# Adds negative weight for sell positions

def get_open_positions_weight():
    initialize_mt5()
    positions = mt5.positions_get()
    if positions is None:
        raise RuntimeError(f"Failed to retrieve positions, error code: {mt5.last_error()}")

    positions_df = pd.DataFrame(list(positions), columns=positions[0]._asdict().keys())
    balance = mt5.account_info().balance
    account_currency = mt5.account_info().currency

    if balance <= 0:
        raise ValueError("Account balance is zero or negative, cannot calculate weights.")

    positions_df['volume'] = positions_df['volume'].astype(float)
    positions_df['price'] = positions_df['price_open'].astype(float)

    # Convert exposure to account currency
    positions_df['exposure'] = positions_df.apply(
        lambda row: convert_to_account_currency(row['symbol'], row['volume'], row['price'], account_currency), axis=1
    )

    # Adjust weight for sell positions
    positions_df['direction'] = positions_df['type'].apply(lambda x: -1 if x == mt5.ORDER_TYPE_SELL else 1)
    positions_df['weight'] = (positions_df['exposure'] * positions_df['direction'] / balance).round(3)
    positions_df['weight_formatted'] = positions_df['weight'].apply(lambda x: f"{x: .0%}")

    return positions_df[['symbol', 'weight', 'weight_formatted','time']]

# Function to get monthly statistics using Duplikum API and convert PnL to account currency
def get_monthly_statistics():
    DUPLIKUM_API_URL = "https://www.trade-copier.com/webservice/v4/reporting/getReporting.php"
    AUTH_USERNAME = "SaadFK"
    AUTH_TOKEN = "jExYzYwMzk1ZWJkZjgwN2JlYTM1ZTQ"

    now = datetime.now()
    month = now.month
    year = now.year

    response = requests.get(DUPLIKUM_API_URL, headers={
        "Auth-Username": AUTH_USERNAME,
        "Auth-Token": AUTH_TOKEN
    }, params={"month": month, "year": year, "limit": 1000})

    if response.status_code != 200:
        raise RuntimeError(f"Failed to fetch monthly statistics. Status code: {response.status_code}, Response: {response.text}")

    stats_data = response.json()

    # Extract the 'reporting' key, which contains the list of rows
    reporting_data = stats_data.get('reporting', [])
    if not reporting_data:
        raise ValueError("No reporting data found in the API response.")

    # Convert the reporting data into a DataFrame
    stats_df = pd.DataFrame(reporting_data)

    account_currency = mt5.account_info().currency

    # Convert PnL to account currency if needed
    def convert_pnl(row):
        if row['currency'] == account_currency:
            return float(row['pnl'])
        conversion_pair = f"{row['currency']}{account_currency}"
        try:
            if mt5.symbol_info(conversion_pair):
                conversion_rate = mt5.symbol_info_tick(conversion_pair).bid
            else:
                conversion_rate = None
        except Exception:
            conversion_rate = None

        if conversion_rate is None:
            reverse_pair = f"{account_currency}{row['currency']}"
            try:
                reverse_rate = mt5.symbol_info_tick(reverse_pair).ask
                if reverse_rate:
                    conversion_rate = 1 / reverse_rate
            except Exception:
                conversion_rate = None

        if conversion_rate is None:
            raise RuntimeError(f"Cannot find conversion rate for {row['currency']} to {account_currency}")
        return float(row['pnl']) * conversion_rate

    # Ensure required columns are present before applying conversion
    if {'currency', 'pnl'}.issubset(stats_df.columns):
        stats_df['pnl_converted'] = stats_df.apply(convert_pnl, axis=1)
    else:
        raise KeyError("Missing required columns: 'currency' or 'pnl'")

    # Sum all converted PnL
    total_pnl = stats_df['pnl_converted'].sum()
    return total_pnl

# Function to calculate the weighted average beta of open positions vs US500
# Now uses the outcome of the first function

def calculate_beta_vs_benchmark():
    initialize_mt5()
    us500_data = mt5.copy_rates_from_pos("US500", mt5.TIMEFRAME_D1, 0, 3 * 252)
    if us500_data is None:
        raise RuntimeError(f"Failed to retrieve US500 data, error code: {mt5.last_error()}")

    us500_df = pd.DataFrame(us500_data)
    us500_df['return'] = us500_df['close'].pct_change()

    positions_df = get_open_positions_weight()

    betas = []

    for _, row in positions_df.iterrows():
        symbol = row['symbol']
        weight = row['weight']

        symbol_data = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 3 * 252)
        if symbol_data is None:
            print(f"Failed to retrieve data for {symbol}, skipping.")
            continue

        symbol_df = pd.DataFrame(symbol_data)
        symbol_df['return'] = symbol_df['close'].pct_change()

        merged_df = pd.merge(symbol_df, us500_df, left_index=True, right_index=True, suffixes=("_symbol", "_benchmark"))
        covariance = np.cov(merged_df['return_symbol'].dropna(), merged_df['return_benchmark'].dropna())[0, 1]
        variance = np.var(merged_df['return_benchmark'].dropna())
        beta = covariance / variance

        betas.append(beta * weight)

    # Calculate weighted average beta
    weighted_average_beta = sum(betas)

    return f"{round(weighted_average_beta, 1)}x"

if __name__ == "__main__":
    initialize_mt5()

    print("Open Positions and Weights:")
    print(get_open_positions_weight())

    print("Monthly Statistics:")
    print(get_monthly_statistics())

    print("Weighted Average Beta vs US500:")
    print(calculate_beta_vs_benchmark())

    mt5.shutdown()
