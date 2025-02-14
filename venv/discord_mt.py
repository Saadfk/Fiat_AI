import discord
from discord.ext import commands
from riskmgr import get_open_positions_weight, get_monthly_statistics, calculate_beta_vs_benchmark, initialize_mt5
import MetaTrader5 as mt5
import pandas as pd
import Keys

# Initialize the bot

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

@bot.command(name="positions")
async def positionsz(ctx):

    try:

        positions_data = get_open_positions_weight()

        # Fetch open positions for additional details
        mt5_positions = mt5.positions_get()
        if mt5_positions is None:
            raise RuntimeError("Failed to retrieve open positions")

        positions_df = pd.DataFrame(list(mt5_positions), columns=mt5_positions[0]._asdict().keys())
        positions_df['price_open'] = positions_df['price_open'].astype(float)
        positions_df['profit'] = positions_df['profit'].astype(float).round(0)

        # Merge additional data with weights
        merged_data = pd.merge(positions_data, positions_df, on="time", how="left")

        formatted_positions = "\n".join([
            f"{row['symbol_x']}: Weight {row['weight_formatted']}, Open Price {row['price_open']:.2f}, P&L {'🟢' if row['profit'] > 0 else '🔴'} {row['profit']:.0f}"
            for _, row in merged_data.iterrows()
        ])
        await ctx.send(f"**Open Positions and Weights:**\n```\n{formatted_positions}\n```")
    except Exception as e:
        await ctx.send(f"Error fetching positions: {str(e)}")
    finally:
        mt5.shutdown()
async def positions(ctx):
    await ctx.send("https://www.myfxbook.com/members/fiatelpis2/fiatelpis-central-iv-fusion/10569665")
@bot.command(name="pnl")
async def pnl(ctx):
    try:
        pnl_data = get_monthly_statistics()
        await ctx.send(f"**Monthly PnL:**\n```\n{pnl_data}\n```")
    except Exception as e:
        await ctx.send(f"Error fetching PnL: {str(e)}")
    finally:
        mt5.shutdown()

@bot.command(name="beta")
async def beta(ctx):

    try:
        beta_data = calculate_beta_vs_benchmark()
        await ctx.send(f"**Weighted Average Beta vs US500:**\n```\n{beta_data}\n```")
    except Exception as e:
        await ctx.send(f"Error fetching beta: {str(e)}")
    finally:
        mt5.shutdown()
import Keys
import discord
from discord.ext import commands
import yfinance as yf
import pandas as pd


@bot.command(name="atm")
async def atm_cmd(ctx, ticker: str):
    """
    Usage: !atm <ticker>
    Example: !atm SPY
    Returns the earliest available option expiration's implied move %
    based on the ATM straddle's mid-prices.
    """
    try:
        # 1) Fetch the ticker object and find the earliest expiration date
        t = yf.Ticker(ticker)
        if not t.options:
            await ctx.send(f"No option expirations found for `{ticker}`.")
            return

        earliest_exp = t.options[0]  # Grab the earliest expiration
        chain = t.option_chain(earliest_exp)
        calls = chain.calls.copy()
        puts = chain.puts.copy()

        if calls.empty or puts.empty:
            await ctx.send(f"No option chain data for `{ticker}` on {earliest_exp}.")
            return

        # 2) Fetch the latest close price for the underlying
        hist = t.history(period="1d")
        if hist.empty:
            await ctx.send(f"No price data found for ticker `{ticker}`.")
            return

        current_price = hist['Close'].iloc[-1]

        # 3) Calculate mid-prices for calls & puts
        calls['mid'] = (calls['bid'] + calls['ask']) / 2
        puts['mid'] = (puts['bid'] + puts['ask']) / 2

        # 4) Identify the ATM call row by minimal distance to current_price
        calls['dist'] = (calls['strike'] - current_price).abs()
        atm_call = calls.loc[calls['dist'].idxmin()]
        atm_strike = atm_call['strike']
        mid_call_price = atm_call['mid']

        # Fallback if mid is missing
        if pd.isnull(mid_call_price):
            mid_call_price = atm_call['lastPrice']

        # 5) Find corresponding put row at the same strike (or nearest if not exact)
        put_row = puts[puts['strike'] == atm_strike]
        if put_row.empty:
            puts['dist'] = (puts['strike'] - current_price).abs()
            put_row = puts.loc[puts['dist'].idxmin()]

        mid_put_price = put_row['mid'].values[0]
        if pd.isnull(mid_put_price):
            mid_put_price = put_row['lastPrice'].values[0]

        # 6) Compute the ATM straddle cost and implied move %
        straddle_cost = mid_call_price + mid_put_price
        implied_move_pct = (straddle_cost / current_price) * 100.0

        # 7) Send a compact message with only the implied move %
        await ctx.send(f"**{ticker.upper()}** | Earliest Exp: {earliest_exp} | "
                       f"ATM Implied Move: **{implied_move_pct:.2f}%**")

    except Exception as e:
        await ctx.send(f"Error computing implied move for `{ticker}`: {str(e)}")


import matplotlib
matplotlib.use("Agg")  # Use a non-GUI backend for servers/environments without a display
import matplotlib.pyplot as plt
import io


@bot.command(name="atm_all")
async def atm_all_cmd(ctx, ticker: str):
    """
    Usage: !atm_all <ticker>
    Example: !atm_all SPY

    - Fetches all option expirations for <ticker> from Yahoo Finance.
    - Calculates the ATM implied move (%) based on mid-prices for each expiration.
    - Creates a matplotlib chart (Expiration vs. Implied Move %) and sends it as an image.
    """
    try:
        t = yf.Ticker(ticker)
        exps = t.options[:10]
        if not exps:
            await ctx.send(f"No option expirations found for `{ticker}`.")
            return

        # Fetch latest close price
        hist = t.history(period="1d")
        if hist.empty:
            await ctx.send(f"No price data found for `{ticker}`.")
            return

        current_price = hist["Close"].iloc[-1]

        # We'll store data here to later create a chart:
        # (expiration_date, implied_move_pct)
        results = []

        for exp_date in exps:
            # Pull the option chain for this expiration
            chain = t.option_chain(exp_date)
            calls = chain.calls.copy()
            puts = chain.puts.copy()

            # Skip if no calls/puts
            if calls.empty or puts.empty:
                continue

            # Calculate mid-prices
            calls["mid"] = (calls["bid"] + calls["ask"]) / 2
            puts["mid"] = (puts["bid"] + puts["ask"]) / 2

            # Identify the ATM strike (closest to current_price)
            calls["dist"] = (calls["strike"] - current_price).abs()
            atm_call = calls.loc[calls["dist"].idxmin()]
            atm_strike = atm_call["strike"]
            mid_call_price = (
                atm_call["mid"]
                if pd.notnull(atm_call["mid"])
                else atm_call["lastPrice"]
            )

            # Find matching put row
            put_row = puts[puts["strike"] == atm_strike]
            if put_row.empty:
                # If not found, pick nearest
                puts["dist"] = (puts["strike"] - current_price).abs()
                put_row = puts.loc[puts["dist"].idxmin()]

            mid_put_price = put_row["mid"].values[0]
            if pd.isnull(mid_put_price):
                mid_put_price = put_row["lastPrice"].values[0]

            # ATM Straddle cost & implied move
            straddle_cost = mid_call_price + mid_put_price
            implied_move_pct = (straddle_cost / current_price) * 100.0

            # Save the result
            results.append((exp_date, implied_move_pct))

        if not results:
            await ctx.send(f"No valid ATM straddle data for `{ticker}`.")
            return

        # Sort results by date (just in case they aren't already)
        # ex: 'YYYY-MM-DD' string -> convert to datetime for sorting
        results.sort(key=lambda x: x[0])

        # Separate the data into lists for plotting
        x_labels = [r[0] for r in results]  # Expiration dates (str)
        y_values = [r[1] for r in results]  # Implied move %

        # Create a matplotlib figure
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(x_labels, y_values, marker='o', linestyle='-', color='b')
        ax.set_title(f"{ticker.upper()} - Implied Move by Expiration")
        ax.set_xlabel("Expiration Date")
        ax.set_ylabel("Implied Move (%)")
        ax.grid(True)
        plt.xticks(rotation=45, ha="right")  # Tilt x labels for readability
        plt.tight_layout()

        # Convert plot to image (in-memory)
        buffer = io.BytesIO()
        plt.savefig(buffer, format="png")
        buffer.seek(0)
        plt.close(fig)  # Close figure to release memory

        # Send the image to Discord
        file = discord.File(fp=buffer, filename="chart.png")
        await ctx.send(file=file)

    except Exception as e:
        await ctx.send(f"Error: {str(e)}")



import discord
from discord.ext import commands
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import io
from datetime import datetime
from scipy.stats import norm
import numpy as np



# Helper function to calculate delta using Black-Scholes formula
def calculate_delta(call_put, S, K, T, r, sigma):
    """
    Calculate the Black-Scholes delta for a call or put option.

    Parameters:
    - call_put (str): 'call' or 'put'
    - S (float): Current stock price
    - K (float): Strike price
    - T (float): Time to expiration in years
    - r (float): Risk-free interest rate
    - sigma (float): Implied volatility

    Returns:
    - delta (float): The delta of the option
    """
    if T <= 0 or sigma <= 0:
        return np.nan

    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    if call_put.lower() == 'call':
        delta = norm.cdf(d1)
    elif call_put.lower() == 'put':
        delta = norm.cdf(d1) - 1
    else:
        delta = np.nan
    return delta


@bot.command(name="Call")
async def call_ticker_cmd(ctx, ticker: str):
    """
    Usage: !call_Ticker <ticker>
    Example: !call_Ticker SPY

    - Fetches up to 10 option expirations for <ticker> from Yahoo Finance.
    - Identifies the 25 delta call for each expiration.
    - Extracts the implied volatility (IV) of the 25 delta call.
    - Creates a matplotlib chart (Expiration vs. Implied Volatility) and sends it as an image.
    """
    try:
        # Initialize ticker
        t = yf.Ticker(ticker)
        exps = t.options[:10]  # Limit to first 10 expirations for performance
        if not exps:
            await ctx.send(f"No option expirations found for `{ticker}`.")
            return

        # Fetch latest close price
        hist = t.history(period="1d")
        if hist.empty:
            await ctx.send(f"No price data found for `{ticker}`.")
            return
        current_price = hist["Close"].iloc[-1]

        # Assume a constant risk-free rate (e.g., 1%)
        risk_free_rate = 0.01

        results = []  # Store (expiration_date, implied_volatility)

        for exp_date in exps:
            try:
                # Fetch option chain for the expiration date
                chain = t.option_chain(exp_date)
                calls = chain.calls

                if calls.empty:
                    continue

                # Drop options with missing implied volatility
                calls = calls.dropna(subset=["impliedVolatility"])

                if calls.empty:
                    continue

                # Calculate time to expiration in years
                exp_datetime = datetime.strptime(exp_date, "%Y-%m-%d")
                today = datetime.utcnow()
                T = (exp_datetime - today).days / 365.25
                if T <= 0:
                    continue

                # Calculate delta for each call option
                calls['delta'] = calls.apply(
                    lambda row: calculate_delta(
                        'call',
                        S=current_price,
                        K=row['strike'],
                        T=T,
                        r=risk_free_rate,
                        sigma=row['impliedVolatility']
                    ),
                    axis=1
                )

                # Drop options with invalid delta
                calls = calls.dropna(subset=["delta"])

                if calls.empty:
                    continue

                # Find the call option with delta closest to 0.25
                calls['delta_diff'] = (calls['delta'] - 0.25).abs()
                atm_call = calls.loc[calls['delta_diff'].idxmin()]

                # Extract implied volatility
                iv = atm_call['impliedVolatility'] * 100  # Convert to percentage

                # Save the result
                results.append((exp_date, iv))

            except Exception as e:
                print(f"Error processing expiration {exp_date}: {e}")
                continue  # Skip problematic expirations

        if not results:
            await ctx.send(f"No valid 25 delta call data found for `{ticker}`.")
            return

        # Sort results by expiration date
        results.sort(key=lambda x: datetime.strptime(x[0], "%Y-%m-%d"))

        # Extract data for plotting
        x_labels, y_values = zip(*results)

        # Create matplotlib figure
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(x_labels, y_values, marker="o", linestyle="-", color="g")
        ax.set_title(f"{ticker.upper()} - Implied Volatility of 25 Delta Calls")
        ax.set_xlabel("Expiration Date")
        ax.set_ylabel("Implied Volatility (%)")
        ax.grid(True)
        plt.xticks(rotation=45, ha="right")  # Tilt x labels for readability
        plt.tight_layout()

        # Convert plot to in-memory image
        buffer = io.BytesIO()
        plt.savefig(buffer, format="png")
        buffer.seek(0)
        plt.close(fig)  # Free memory

        # Send chart to Discord
        file = discord.File(fp=buffer, filename="iv_chart.png")
        await ctx.send(file=file)

    except Exception as e:
        await ctx.send(f"Error: {str(e)}")


if __name__ == "__main__":
    TOKEN = Keys.DISCORD_BOT_TOKEN
    bot.run(TOKEN)
