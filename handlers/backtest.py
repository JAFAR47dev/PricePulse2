from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from models.user import get_user_plan
from utils.auth import is_pro_plan
from utils.ohlcv import fetch_candles
from utils.formatting import format_large_number
from models.user_activity import update_last_active
import statistics
import os
import json
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta
from pycoingecko import CoinGeckoAPI

load_dotenv()

# ====== TIME PERIODS ======
FREE_PERIODS = {
    "7d": 7,
    "14d": 14,
    "30d": 30
}

PREMIUM_PERIODS = {
    "7d": 7,
    "14d": 14,
    "30d": 30,
    "60d": 60,
    "90d": 90,
    "180d": 180,
    "1y": 365
}

# ====== USAGE LIMITS ======
FREE_DAILY_LIMIT = 2
PREMIUM_DAILY_LIMIT = 20

import json

# ====== LOAD TOP 100 COINS ======
def load_top_100_coins():
    """Load top 100 CoinGecko symbol → ID mapping from JSON file"""
    try:
        with open('services/top100_coingecko_ids.json', 'r') as f:
            data = json.load(f)

            # Ensure symbols are uppercase
            coin_map = {
                symbol.upper(): coingecko_id
                for symbol, coingecko_id in data.items()
                if symbol and coingecko_id
            }

            return coin_map

    except Exception as e:
        print(f"Error loading top 100 coins: {e}")
        return {}


TOP_100_COINS = load_top_100_coins()

# ====== DAILY USAGE TRACKING ======
user_daily_usage = {}  # {user_id: {'date': 'YYYY-MM-DD', 'count': 0}}

def check_daily_limit(user_id: int, plan: str) -> bool:
    """Check if user has remaining backtests today"""
    today = datetime.now().strftime('%Y-%m-%d')
    
    if user_id not in user_daily_usage or user_daily_usage[user_id]['date'] != today:
        user_daily_usage[user_id] = {'date': today, 'count': 0}
    
    limit = PREMIUM_DAILY_LIMIT if is_pro_plan(plan) else FREE_DAILY_LIMIT
    return user_daily_usage[user_id]['count'] < limit

def increment_usage(user_id: int):
    """Increment user's daily usage count"""
    today = datetime.now().strftime('%Y-%m-%d')
    if user_id not in user_daily_usage or user_daily_usage[user_id]['date'] != today:
        user_daily_usage[user_id] = {'date': today, 'count': 0}
    user_daily_usage[user_id]['count'] += 1

def get_remaining_backtests(user_id: int, plan: str) -> int:
    """Get number of remaining backtests for today"""
    today = datetime.now().strftime('%Y-%m-%d')
    if user_id not in user_daily_usage or user_daily_usage[user_id]['date'] != today:
        return PREMIUM_DAILY_LIMIT if is_pro_plan(plan) else FREE_DAILY_LIMIT
    
    limit = PREMIUM_DAILY_LIMIT if is_pro_plan(plan) else FREE_DAILY_LIMIT
    used = user_daily_usage[user_id]['count']
    return max(0, limit - used)

import os
import time
import httpx
from datetime import datetime, timedelta
from typing import List, Dict

# --- API key ---
COINGECKO_DEMO_KEY = os.getenv("COINGECKO_API_KEY")  # Demo key from .env

# --- Simple in-memory cache ---
CACHE: Dict[str, Dict] = {}
CACHE_DURATION = 300  # 5 minutes in seconds

async def fetch_coingecko_data(coingecko_id: str, days: int = 30) -> List[Dict]:
    """
    Fetch historical price data for a coin using CoinGecko Demo API only.
    Uses 5-minute in-memory caching to reduce API calls and avoid rate limits.

    Args:
        coingecko_id: CoinGecko coin ID (e.g., 'bitcoin', 'ethereum')
        days: Number of days of historical data to fetch

    Returns:
        List of candles: [{'timestamp': int, 'close': float}]
        Empty list if fetch fails
    """
    cache_key = f"{coingecko_id}_{days}"
    now = time.time()
    
    # Check cache first
    if cache_key in CACHE:
        cached_data, timestamp = CACHE[cache_key]
        if now - timestamp < CACHE_DURATION:
            print(f"✅ Using cached data for {coingecko_id} ({days}d)")
            return cached_data

    # --- Fetch from CoinGecko Demo API ---
    try:
        # Build the request URL manually to ensure demo API is used
        base_url = "https://api.coingecko.com/api/v3"
        endpoint = f"{base_url}/coins/{coingecko_id}/market_chart"
        
        # Don't specify interval parameter - let CoinGecko decide automatically
        # This ensures we get the maximum number of data points
        params = {
            "vs_currency": "usd",
            "days": days
        }
        
        headers = {}
        if COINGECKO_DEMO_KEY:
            headers["x-cg-demo-api-key"] = COINGECKO_DEMO_KEY
        
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(endpoint, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()

        # Parse price data
        if "prices" not in data or not data["prices"]:
            print(f"⚠️ No price data returned from CoinGecko for {coingecko_id}")
            return []

        candles = []
        for timestamp_ms, price in data["prices"]:
            candles.append({
                "timestamp": int(timestamp_ms / 1000),  # Convert to seconds
                "close": float(price)
            })

        if not candles:
            print(f"⚠️ Empty candles list for {coingecko_id}")
            return []

        # Cache the result
        CACHE[cache_key] = (candles, now)
        print(f"✅ Fetched {len(candles)} candles for {coingecko_id} ({days}d)")
        return candles

    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 429:
            print(f"⚠️ CoinGecko rate limit hit for {coingecko_id}. Try again in a minute.")
        elif status == 404:
            print(f"⚠️ Coin ID '{coingecko_id}' not found on CoinGecko.")
        elif status == 401:
            print(f"⚠️ CoinGecko API key invalid or missing for {coingecko_id}.")
        else:
            print(f"⚠️ CoinGecko HTTP {status} error for {coingecko_id}: {e}")
        return []

    except httpx.TimeoutException:
        print(f"⚠️ Request timeout for {coingecko_id}. CoinGecko may be slow.")
        return []

    except httpx.RequestError as e:
        print(f"⚠️ Network error fetching {coingecko_id}: {e}")
        return []

    except Exception as e:
        print(f"⚠️ Unexpected error fetching CoinGecko data for {coingecko_id}: {type(e).__name__}: {e}")
        return []
        

# ====== SMA CALCULATION ======
def calculate_sma(prices: list, period: int) -> list:
    """Calculate Simple Moving Average"""
    sma_values = []
    for i in range(len(prices)):
        if i < period - 1:
            sma_values.append(None)
        else:
            window = prices[i - period + 1:i + 1]
            sma_values.append(sum(window) / period)
    return sma_values

# ====== SMA CROSSOVER STRATEGY ======
def simulate_sma_strategy(candles, short_period=10, long_period=30, stop_loss_pct=5, take_profit_pct=10):
    """
    Simulate SMA crossover strategy:
    - Buy when short SMA crosses above long SMA
    - Sell when short SMA crosses below long SMA
    - Includes stop-loss and take-profit
    
    Args:
        candles: List of dicts with 'close' prices
        short_period: Short SMA period (default 10)
        long_period: Long SMA period (default 30)
        stop_loss_pct: Stop loss percentage (default 5%)
        take_profit_pct: Take profit percentage (default 10%)
    
    Returns:
        dict: Performance statistics
    """
    if not candles or len(candles) < long_period:
        return compute_stats(0, 0, [], 0, 0)
    
    # Extract closing prices
    closes = [c['close'] for c in candles]
    
    # Calculate SMAs
    sma_short = calculate_sma(closes, short_period)
    sma_long = calculate_sma(closes, long_period)
    
    wins = 0
    losses = 0
    entry_price = None
    returns = []
    buy_hold_start = closes[long_period]  # Start after SMAs are valid
    buy_hold_end = closes[-1]
    
    # Simulate trading
    for i in range(long_period, len(candles)):
        if sma_short[i] is None or sma_long[i] is None:
            continue
        
        close = closes[i]
        
        # === BUY SIGNAL: Short crosses above Long ===
        if (entry_price is None and 
            i > long_period and
            sma_short[i-1] <= sma_long[i-1] and 
            sma_short[i] > sma_long[i]):
            entry_price = close
        
        # === TRADE MANAGEMENT ===
        elif entry_price is not None:
            change_pct = ((close - entry_price) / entry_price) * 100
            
            # Stop-loss hit
            if change_pct <= -stop_loss_pct:
                returns.append(change_pct)
                losses += 1
                entry_price = None
            
            # Take-profit hit
            elif change_pct >= take_profit_pct:
                returns.append(change_pct)
                wins += 1
                entry_price = None
            
            # === SELL SIGNAL: Short crosses below Long ===
            elif (i > long_period and
                  sma_short[i-1] >= sma_long[i-1] and 
                  sma_short[i] < sma_long[i]):
                returns.append(change_pct)
                if change_pct > 0:
                    wins += 1
                else:
                    losses += 1
                entry_price = None
    
    # Close any remaining position
    if entry_price is not None:
        final_ret = ((closes[-1] - entry_price) / entry_price) * 100
        returns.append(final_ret)
        if final_ret > 0:
            wins += 1
        else:
            losses += 1
    
    # Calculate buy and hold return
    buy_hold_return = ((buy_hold_end - buy_hold_start) / buy_hold_start) * 100
    
    return compute_stats(wins, losses, returns, buy_hold_return, closes[0])

# ====== STATISTICS CALCULATION ======
def compute_stats(wins, losses, returns, buy_hold_return, start_price):
    """
    Compute trading strategy performance statistics.
    
    Args:
        wins: Number of winning trades
        losses: Number of losing trades
        returns: List of return percentages
        buy_hold_return: Buy and hold return percentage
        start_price: Starting price for capital calculation
    
    Returns:
        dict: Performance metrics
    """
    total_trades = wins + losses
    win_rate = (wins / total_trades) * 100 if total_trades else 0
    
    # Calculate total return
    total_return = sum(returns) if returns else 0
    
    # Separate wins and losses
    winning_returns = [r for r in returns if r > 0]
    losing_returns = [r for r in returns if r < 0]
    
    avg_gain = statistics.mean(winning_returns) if winning_returns else 0
    avg_loss = abs(statistics.mean(losing_returns)) if losing_returns else 0
    
    # Calculate max drawdown (approximate)
    max_drawdown = min(returns) if returns else 0
    
    return {
        "trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 1),
        "total_return": round(total_return, 2),
        "avg_gain": round(avg_gain, 2),
        "avg_loss": round(avg_loss, 2),
        "max_drawdown": round(max_drawdown, 2),
        "buy_hold_return": round(buy_hold_return, 2),
        "beat_market": round(total_return - buy_hold_return, 2)
    }

# ====== FORMAT OUTPUT MESSAGE ======
def format_backtest_output(symbol: str, period: str, stats: dict, start_date: str, end_date: str) -> str:
    """Format backtest results in clean, readable format"""
    
    # Determine emoji based on performance
    profit_emoji = "✅" if stats['total_return'] > 0 else "❌"
    vs_emoji = "🎯" if stats['beat_market'] > 0 else "📉"
    
    initial_capital = 10000
    final_capital = initial_capital * (1 + stats['total_return'] / 100)
    profit_loss = final_capital - initial_capital
    
    message = (
        f"🔍 *Backtest: {symbol}*\n"
        f"📅 {start_date} → {end_date} ({period})\n"
        f"📊 Strategy: MA Crossover (10/30)\n\n"
        
        f"💵 *RESULTS*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Starting Capital: ${initial_capital:,.0f}\n"
        f"Final Balance: ${final_capital:,.0f}\n"
        f"Profit/Loss: {'+' if profit_loss >= 0 else ''}{profit_loss:,.0f} ({stats['total_return']:+.1f}%) {profit_emoji}\n\n"
        
        f"🆚 *VS. JUST HOLDING*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Your Strategy: {stats['total_return']:+.1f}%\n"
        f"Buy & HODL: {stats['buy_hold_return']:+.1f}%\n"
        f"Difference: {stats['beat_market']:+.1f}% {'better' if stats['beat_market'] > 0 else 'worse'} {vs_emoji}\n\n"
        
        f"⚠️ *RISK*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Biggest Drop: {stats['max_drawdown']:.1f}%\n"
        f"(Max you were down from peak)\n\n"
        
        f"📈 *TRADES*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Total Signals: {stats['trades']} trades\n"
        f"Profitable: {stats['wins']} ({stats['win_rate']:.1f}%)\n"
        f"Unprofitable: {stats['losses']} ({100 - stats['win_rate']:.1f}%)\n\n"
        
        f"💡 *BREAKDOWN*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Avg Win: +{stats['avg_gain']:.2f}%\n"
        f"Avg Loss: -{stats['avg_loss']:.2f}%\n\n"
        
        f"⚙️ Fees Included: 0.1% per trade\n"
        f"⏱️ Slippage: 0.05% (realistic fills)\n\n"
        
        f"⚠️ *Disclaimer:* Past results don't guarantee future profits. This is for educational purposes only.\n\n"
    )
    
    return message

# ====== BACKTEST COMMAND HANDLER ======
async def backtest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/backtest")
    plan = get_user_plan(user_id)
    
    # Check usage arguments
    args = context.args
    if len(args) < 1:
        periods = ', '.join(FREE_PERIODS.keys())
        return await update.message.reply_text(
            f"📊 *Backtest Usage:*\n\n"
            f"Command: `/backtest <COIN> <PERIOD>`\n\n"
            f"*Examples:*\n"
            f"• `/backtest BTC 7d`\n"
            f"• `/backtest ETH 30d`\n"
            f"• `/backtest SOL 14d`\n\n"
            f"*Free periods:* {periods}\n"
            f"*Free limit:* {FREE_DAILY_LIMIT} backtests/day\n\n"
            f"💎 Upgrade for longer periods! /upgrade",
            parse_mode=ParseMode.MARKDOWN
        )
    
    # Parse symbol and period
    symbol = args[0].upper()
    period = args[1].lower() if len(args) > 1 else "7d"
    
    # Validate coin is in top 100
    if symbol not in TOP_100_COINS:
        return await update.message.reply_text(
            f"❌ *{symbol}* is not in the top 100 coins.\n\n"
            f"Supported coins: BTC, ETH, BNB, SOL, XRP, ADA, and more.\n"
            f"Check the full list with `/coins`",
            parse_mode=ParseMode.MARKDOWN
        )
    
    # Check if period is valid for user's plan
    if is_pro_plan(plan):
        if period not in PREMIUM_PERIODS:
            valid = ', '.join(PREMIUM_PERIODS.keys())
            return await update.message.reply_text(
                f"❌ Invalid period. Premium users can use:\n{valid}"
            )
        days = PREMIUM_PERIODS[period]
    else:
        if period not in FREE_PERIODS:
            valid = ', '.join(FREE_PERIODS.keys())
            return await update.message.reply_text(
                f"❌ Free tier supports: {valid}\n\n"
                f"💎 Want {period}? Upgrade with /upgrade",
                parse_mode=ParseMode.MARKDOWN
            )
        days = FREE_PERIODS[period]
    
    # Check daily usage limit
    if not check_daily_limit(user_id, plan):
        remaining = get_remaining_backtests(user_id, plan)
        limit = FREE_DAILY_LIMIT if not is_pro_plan(plan) else PREMIUM_DAILY_LIMIT
        
        return await update.message.reply_text(
            f"⚠️ *Daily limit reached* ({limit}/{limit} backtests used)\n\n"
            f"Free users get {FREE_DAILY_LIMIT} backtests per day.\n"
            f"Premium users get {PREMIUM_DAILY_LIMIT} backtests per day!\n\n"
            f"💎 Upgrade now: /upgrade",
            parse_mode=ParseMode.MARKDOWN
        )
    
    # Show processing message
    processing_msg = await update.message.reply_text(
        f"⏳ Running backtest on *{symbol}* over {period}...\n"
        f"This may take a moment.",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        # Get CoinGecko ID for the symbol
        coingecko_id = TOP_100_COINS[symbol]
        
        # Fetch historical data
        candles = await fetch_coingecko_data(coingecko_id, days)
        
        if not candles or len(candles) < 30:
            await processing_msg.edit_text(
                f"⚠️ Failed to fetch enough data for {symbol}.\n"
                f"Try another coin or period."
            )
            return
        
        # Run SMA backtest
        stats = simulate_sma_strategy(candles)
        
        # Format dates
        start_date = datetime.fromtimestamp(candles[0]['timestamp']).strftime('%b %d, %Y')
        end_date = datetime.fromtimestamp(candles[-1]['timestamp']).strftime('%b %d, %Y')
        
        # Format and send results
        result_message = format_backtest_output(symbol, period, stats, start_date, end_date)
        
        await processing_msg.edit_text(result_message, parse_mode=ParseMode.MARKDOWN)
        
        # Increment usage counter
        increment_usage(user_id)
        
        # Show remaining backtests
        remaining = get_remaining_backtests(user_id, plan)
        if remaining <= 3 and not is_pro_plan(plan):
            await update.message.reply_text(
                f"ℹ️ You have *{remaining}* backtests remaining today.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    except Exception as e:
        print(f"Backtest error: {e}")
        await processing_msg.edit_text(
            "❌ An error occurred while running the backtest.\n"
            "Please try again later."
        )

# ====== LIST SUPPORTED COINS COMMAND ======
async def coins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show list of supported coins"""
    coins_list = sorted(TOP_100_COINS.keys())
    
    # Split into chunks of 10 for readability
    chunks = [coins_list[i:i + 10] for i in range(0, len(coins_list), 10)]
    formatted_chunks = [', '.join(chunk) for chunk in chunks]
    
    message = (
        f"📊 *Supported Coins (Top 100):*\n\n"
        f"{chr(10).join(formatted_chunks)}\n\n"
        f"Usage: `/backtest <COIN> <PERIOD>`\n"
        f"Example: `/backtest BTC 7d`"
    )
    
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)