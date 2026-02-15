from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CallbackQueryHandler
from models.user import get_user_plan
from utils.auth import is_pro_plan
from models.user_activity import update_last_active
from tasks.handlers import handle_streak
from models.sma_strategy import simulate_sma_strategy
from models.rsi_strategy import simulate_rsi_strategy
from utils.backtest_formatter import format_strategy_output, format_comparison_output
import json
from datetime import datetime

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

# ====== LOAD TOP 100 COINS ======
def load_top_100_coins():
    """Load top 100 CoinGecko symbol → ID mapping from JSON file"""
    try:
        with open('services/top100_coingecko_ids.json', 'r') as f:
            data = json.load(f)
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
    from utils.auth import is_pro_plan
    
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
    from utils.auth import is_pro_plan
    
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
        
    
async def backtest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Main backtest command - shows strategy selection buttons
    """
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/backtest")
    await handle_streak(update, context)
    plan = get_user_plan(user_id)
    
    args = context.args
    if len(args) < 1:
        periods = ', '.join(FREE_PERIODS.keys())
        return await update.message.reply_text(
            f"📊 *Backtest Usage:*\n\n"
            f"Command: `/backtest <COIN> <PERIOD>`\n\n"
            f"*Examples:*\n"
            f"• `/bt BTC 7d`\n"
            f"• `/bt ETH 30d`\n"
            f"• `/bt SOL 14d`\n\n"
            f"*Free periods:* {periods}\n"
            f"*Free limit:* {FREE_DAILY_LIMIT} backtests/day\n\n"
            f"💎 Upgrade for longer periods! /upgrade",
            parse_mode=ParseMode.MARKDOWN
        )
    
    # Parse symbol and period
    symbol = args[0].upper()
    period = args[1].lower() if len(args) > 1 else "7d"
    
    # Validate coin
    if symbol not in TOP_100_COINS:
        return await update.message.reply_text(
            f"❌ *{symbol}* is not in the top 100 coins.\n\n"
            f"Supported coins: BTC, ETH, BNB, SOL, XRP, ADA, and more.\n"
            f"Check the full list with `/coins`",
            parse_mode=ParseMode.MARKDOWN
        )
    
    # Validate period
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
    
    # Check daily limit
    if not check_daily_limit(user_id, plan):
        limit = FREE_DAILY_LIMIT if not is_pro_plan(plan) else PREMIUM_DAILY_LIMIT
        return await update.message.reply_text(
            f"⚠️ *Daily limit reached* ({limit}/{limit} backtests used)\n\n"
            f"Free users get {FREE_DAILY_LIMIT} backtests per day.\n"
            f"Premium users get {PREMIUM_DAILY_LIMIT} backtests per day!\n\n"
            f"💎 Upgrade now: /upgrade",
            parse_mode=ParseMode.MARKDOWN
        )
    
    # Show strategy selection buttons
    keyboard = [
        [
            InlineKeyboardButton("📈 MA Crossover", callback_data=f"bt_ma_{symbol}_{period}"),
            InlineKeyboardButton("📊 RSI Reversion", callback_data=f"bt_rsi_{symbol}_{period}")
        ],
        [
            InlineKeyboardButton("⚔️ Compare Both", callback_data=f"bt_compare_{symbol}_{period}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📊 *Choose a strategy for {symbol} ({period}):*\n\n"
        f"📈 *MA Crossover* - Trend following (10/30 SMA)\n"
        f"📊 *RSI Reversion* - Mean reversion (RSI 14)\n"
        f"⚔️ *Compare Both* - See which performs better\n\n"
        f"Select a strategy below:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )


async def backtest_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle button callbacks for strategy selection
    """
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    plan = get_user_plan(user_id)
    
    # Parse callback data: bt_<strategy>_<symbol>_<period>
    parts = query.data.split('_')
    if len(parts) < 4:
        return await query.edit_message_text("❌ Invalid selection")
    
    strategy = parts[1]  # 'ma', 'rsi', or 'compare'
    symbol = parts[2]
    period = parts[3]
    
    # Validate period again
    if is_pro_plan(plan):
        days = PREMIUM_PERIODS.get(period)
    else:
        days = FREE_PERIODS.get(period)
    
    if not days:
        return await query.edit_message_text("❌ Invalid period")
    
    # Check daily limit again
    if not check_daily_limit(user_id, plan):
        limit = FREE_DAILY_LIMIT if not is_pro_plan(plan) else PREMIUM_DAILY_LIMIT
        return await query.edit_message_text(
            f"⚠️ *Daily limit reached* ({limit}/{limit} backtests used)\n\n"
            f"💎 Upgrade for more: /upgrade",
            parse_mode=ParseMode.MARKDOWN
        )
    
    # Show processing message
    await query.edit_message_text(
        f"⏳ Running backtest on *{symbol}* ({period})...\n"
        f"This may take a moment.",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        # Get CoinGecko ID
        coingecko_id = TOP_100_COINS[symbol]
        
        # Fetch historical data
        candles = await fetch_coingecko_data(coingecko_id, days)
        
        if not candles or len(candles) < 30:
            return await query.edit_message_text(
                f"⚠️ Failed to fetch enough data for {symbol}.\n"
                f"Try another coin or period."
            )
        
        # Format dates
        start_date = datetime.fromtimestamp(candles[0]['timestamp']).strftime('%b %d, %Y')
        end_date = datetime.fromtimestamp(candles[-1]['timestamp']).strftime('%b %d, %Y')
        
        # Execute strategy based on selection
        if strategy == 'ma':
            stats = simulate_sma_strategy(candles)
            result = format_strategy_output(
                symbol, period, stats, start_date, end_date, 
                "MA Crossover (10/30)"
            )
            increment_usage(user_id)
            
        elif strategy == 'rsi':
            stats = simulate_rsi_strategy(candles)
            result = format_strategy_output(
                symbol, period, stats, start_date, end_date,
                "RSI Reversion (14)"
            )
            increment_usage(user_id)
            
        elif strategy == 'compare':
            sma_stats = simulate_sma_strategy(candles)
            rsi_stats = simulate_rsi_strategy(candles)
            result = format_comparison_output(
                symbol, period, sma_stats, rsi_stats, start_date, end_date
            )
            increment_usage(user_id)
        
        else:
            return await query.edit_message_text("❌ Unknown strategy")
        
        # Send results
        await query.edit_message_text(result, parse_mode=ParseMode.MARKDOWN)
        
        # Show remaining backtests
        remaining = get_remaining_backtests(user_id, plan)
        if remaining <= 3 and not is_pro_plan(plan):
            await query.message.reply_text(
                f"ℹ️ You have *{remaining}* backtests remaining today.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    except Exception as e:
        print(f"Backtest callback error: {e}")
        await query.edit_message_text(
            "❌ An error occurred while running the backtest.\n"
            "Please try again later."
        )
