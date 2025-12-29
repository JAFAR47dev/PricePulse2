# handlers/markets.py
import requests
import json
import os
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from tasks.handlers import handle_streak
from models.user_activity import update_last_active
from typing import Optional, List, Tuple
import logging

# Set up logging
logger = logging.getLogger(__name__)

# Load CoinGecko ID mappings with error handling
COINGECKO_IDS = {}
try:
    with open("utils/coingecko_ids.json", "r") as f:
        COINGECKO_IDS = json.load(f)
except FileNotFoundError:
    logger.error("coingecko_ids.json file not found")
except json.JSONDecodeError:
    logger.error("Invalid JSON in coingecko_ids.json")

# Constants
REQUEST_TIMEOUT = 10  # seconds
MAX_RETRIES = 3
TOP_MARKETS_COUNT = 10

def safe_float(value, default: float = 0.0) -> float:
    """Safely convert value to float with fallback."""
    try:
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        return default

def format_large_number(num: float) -> str:
    """Format large numbers with appropriate suffix."""
    if num >= 1_000_000_000:
        return f"${num/1_000_000_000:.2f}B"
    elif num >= 1_000_000:
        return f"${num/1_000_000:.2f}M"
    elif num >= 1_000:
        return f"${num/1_000:.2f}K"
    else:
        return f"${num:.2f}"

def escape_markdown(text: str) -> str:
    """Escape special markdown characters."""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

async def markets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Fetch and display market prices for a cryptocurrency across different exchanges.
    Usage: /markets [coin_symbol]
    """
    try:
        user_id = update.effective_user.id
        
        # Update user activity
        try:
            await update_last_active(user_id, command_name="/markets")
            await handle_streak(update, context)
        except Exception as e:
            logger.warning(f"Failed to update user activity: {e}")
        
        # Validate input
        if not context.args or len(context.args) != 1:
            await update.message.reply_text(
                "❌ *Usage:* `/markets [coin]`\n"
                "Example: `/markets BTC`",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        symbol = context.args[0].upper().strip()
        
        # Validate symbol
        if not symbol.isalnum():
            await update.message.reply_text("❌ Invalid coin symbol. Please use alphanumeric characters only.")
            return
        
        # Check if coin is supported
        coin_id = COINGECKO_IDS.get(symbol)
        if not coin_id:
            await update.message.reply_text(
                f"❌ Coin symbol `{escape_markdown(symbol)}` not found\\.\n"
                "Please check the symbol and try again\\.",
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        # Send "loading" message
        status_message = await update.message.reply_text(
            f"🔍 Fetching market data for *{symbol}*...",
            parse_mode=ParseMode.MARKDOWN
        )

        # Fetch market data
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/tickers"
        params = {
            "include_exchange_logo": "false",
            "order": "volume_desc"
        }
        
        headers = {
            "User-Agent": "TelegramBot/1.0"
        }

        response = requests.get(
            url, 
            params=params, 
            headers=headers,
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        data = response.json()
        
        tickers = data.get("tickers", [])
        
        if not tickers:
            await status_message.edit_text(
                f"❌ No market data available for *{symbol}* at this time.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Process ticker data
        results: List[Tuple[str, str, float, float]] = []
        for ticker in tickers[:TOP_MARKETS_COUNT * 2]:  # Get more to filter
            try:
                market_name = ticker.get("market", {}).get("name", "Unknown")
                base = ticker.get("base", "")
                target = ticker.get("target", "")
                
                # Skip if missing critical data
                if not base or not target:
                    continue
                
                pair = f"{base}/{target}"
                price = safe_float(ticker.get("last"))
                volume = safe_float(ticker.get("volume"))
                
                # Only include tickers with valid price and volume
                if price > 0 and volume > 0:
                    results.append((market_name, pair, price, volume))
                    
            except Exception as e:
                logger.warning(f"Error processing ticker: {e}")
                continue

        if not results:
            await status_message.edit_text(
                f"❌ No valid market data found for *{symbol}*.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        # Sort by price (descending) and limit to top markets
        results.sort(key=lambda x: x[2], reverse=True)
        results = results[:TOP_MARKETS_COUNT]
        
        # Calculate statistics
        prices = [r[2] for r in results]
        highest = max(prices)
        lowest = min(prices)
        spread = highest - lowest
        spread_pct = (spread / lowest) * 100 if lowest > 0 else 0
        avg_price = sum(prices) / len(prices)

        # Build response message
        text = f"🌍 *{symbol} Market Overview*\n"
        text += f"━━━━━━━━━━━━━━━━\n"
        text += f"🔺 Highest: *${highest:,.2f}*\n"
        text += f"🔻 Lowest: *${lowest:,.2f}*\n"
        text += f"📊 Average: *${avg_price:,.2f}*\n"
        text += f"📈 Spread: *{spread_pct:.2f}%* (${spread:,.2f})\n"
        text += f"━━━━━━━━━━━━━━━━\n\n"

        for idx, (market, pair, price, volume) in enumerate(results, 1):
            # Add indicator for highest/lowest
            indicator = ""
            if price == highest:
                indicator = "🔺 "
            elif price == lowest:
                indicator = "🔻 "
            
            # Truncate long market names
            market_display = market[:20] + "..." if len(market) > 20 else market
            
            text += f"{indicator}*{idx}. {market_display}*\n"
            text += f"   {pair}: *${price:,.2f}*\n"
            text += f"   Vol: {format_large_number(volume)}\n\n"

        text += f"_Data from CoinGecko • {len(results)} markets shown_"

        # Update the status message with results
        await status_message.edit_text(text, parse_mode=ParseMode.MARKDOWN)

    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching market data for {symbol}")
        await update.message.reply_text(
            "⚠️ Request timed out. The API might be slow. Please try again later."
        )
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error fetching market data: {e}")
        if e.response.status_code == 429:
            await update.message.reply_text(
                "⚠️ Rate limit reached. Please wait a moment and try again."
            )
        else:
            await update.message.reply_text(
                f"⚠️ API error ({e.response.status_code}). Please try again later."
            )
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error fetching market data: {e}")
        await update.message.reply_text(
            "⚠️ Network error. Please check your connection and try again."
        )
    except Exception as e:
        logger.error(f"Unexpected error in markets_command: {e}", exc_info=True)
        await update.message.reply_text(
            "⚠️ An unexpected error occurred. Please try again later."
        )