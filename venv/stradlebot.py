import datetime
import pandas as pd
import yfinance as yf


def get_next_n_business_days(n=7):
    """
    Return a list of the next n business days (including today if it's a business day),
    as datetime.date objects.
    """
    business_days = []
    current_date = datetime.date.today()
    while len(business_days) < n:
        # Check if current_date is a weekend (Saturday=5, Sunday=6)
        if current_date.weekday() < 5:  # Monday=0, Tuesday=1, ..., Friday=4
            business_days.append(current_date)
        current_date += datetime.timedelta(days=1)
    return business_days


def format_date(dt):
    """
    Convert a datetime.date (or datetime.datetime) to a 'YYYY-MM-DD' string.
    """
    return dt.strftime('%Y-%m-%d')


def get_atm_straddle_price(ticker_symbol, expiration_date):
    """
    Retrieves the call and put option chains for the given ticker and expiration date,
    finds the closest-to-ATM strike, and computes the total straddle price
    (Call + Put at that strike).

    :param ticker_symbol: str, e.g. "SPY"
    :param expiration_date: str in format 'YYYY-MM-DD', e.g. "2025-01-17"
    :return: (atm_strike, call_price, put_price, straddle_price)
    """
    # 1) Fetch the latest close price for the underlying
    ticker = yf.Ticker(ticker_symbol)
    hist = ticker.history(period="1d")
    if hist.empty:
        raise ValueError(f"No price data found for ticker {ticker_symbol}.")
    current_price = hist['Close'].iloc[-1]

    # 2) Get the option chain for the specific expiration
    #    (This can fail if the expiration doesn't exist)
    try:
        chain = ticker.option_chain(expiration_date)
    except IndexError:
        raise ValueError(f"Expiration {expiration_date} not found for {ticker_symbol}.")

    calls = chain.calls.copy()
    puts = chain.puts.copy()

    if calls.empty or puts.empty:
        raise ValueError(f"No option chain data for {ticker_symbol} on {expiration_date}.")

    # 3) Identify the ATM strike by minimal distance from current price
    calls['distance'] = (calls['strike'] - current_price).abs()
    atm_call_row = calls.loc[calls['distance'].idxmin()]  # row with minimum distance
    atm_strike = atm_call_row['strike']

    # 4) Find the call price at that ATM strike
    #    (We'll use lastPrice for simplicity. Alternatively, you could use bid/ask)
    call_price = atm_call_row['lastPrice']

    # 5) Find the corresponding put price at that same strike
    put_row = puts[puts['strike'] == atm_strike]
    if put_row.empty:
        # If the exact strike doesn't exist in the puts DF, pick the closest
        puts['distance'] = (puts['strike'] - current_price).abs()
        put_row = puts.loc[puts['distance'].idxmin()]
    put_price = put_row['lastPrice'].values[0]  # since put_row is likely a single-row DF

    # 6) Sum up the call + put (the ATM straddle price)
    straddle_price = call_price + put_price

    return atm_strike, call_price, put_price, straddle_price


def implied_expected_move(ticker_symbol, expiration_date):
    """
    Returns a simple approximation of the 'expected move' by expiration,
    based on the ATM straddle price relative to the current underlying price.
    """
    ticker = yf.Ticker(ticker_symbol)
    hist = ticker.history(period="1d")
    current_price = hist['Close'].iloc[-1]

    _, _, _, straddle_price = get_atm_straddle_price(ticker_symbol, expiration_date)

    # A rough measure of “expected move” by that expiration date is simply the straddle cost.
    expected_move = straddle_price

    # Convert to a percentage of the current underlying price
    expected_move_pct = (expected_move / current_price) * 100.0

    return expected_move, expected_move_pct


if __name__ == "__main__":
    my_ticker = "SPY"

    # Get all available option expirations for this ticker
    ticker_obj = yf.Ticker(my_ticker)
    all_expirations = ticker_obj.options  # list of strings in 'YYYY-MM-DD' format

    # Get the next 7 business days from "today"
    next_7_days = get_next_n_business_days(7)
    next_7_days_str = [format_date(d) for d in next_7_days]

    # Filter which of those days are in the actual option expirations on Yahoo
    matching_expirations = [day for day in next_7_days_str if day in all_expirations]

    print(f"\nUnderlying Ticker: {my_ticker}")
    print(f"Next 7 business days: {next_7_days_str}")
    print(f"Available Expirations (Yahoo):")
    print(all_expirations)
    print(f"\nExpirations in the Next 7 Days that Actually Exist on Yahoo Finance:")
    print(matching_expirations)

    print("\n=== ATM Straddle Prices for Next 7 Business Days (If Available) ===")
    for exp_date in matching_expirations:
        try:
            atm_strike, call_price, put_price, straddle_cost = get_atm_straddle_price(my_ticker, exp_date)
            move, move_pct = implied_expected_move(my_ticker, exp_date)
            print(f"\nExpiration: {exp_date}")
            print(f"  ATM Strike: {atm_strike:.2f}")
            print(f"  Call Price: {call_price:.2f}")
            print(f"  Put Price:  {put_price:.2f}")
            print(f"  Straddle Cost: {straddle_cost:.2f}")
            print(f"  Implied Move:  ~{move:.2f} pts ({move_pct:.2f}%)")
        except Exception as e:
            print(f"  Could not compute straddle for {exp_date}. Reason: {str(e)}")
