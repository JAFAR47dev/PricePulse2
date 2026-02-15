"""
Enhanced Global Crypto Market Overview Handler
Includes caching, comprehensive error handling, and optimized API usage
"""

import os
import time
import requests
from typing import Optional, Dict, Tuple
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from tasks.handlers import handle_streak
from models.user_activity import update_last_active


# ============================================================================
# DATA FUNCTION (for notifications)
# ============================================================================

def get_global_market_data() -> dict:
    """
    Fetch global market data and return raw data as dict.
    
    Returns:
        dict: {
            'market_cap': str,
            'volume': str,
            'change': str,
            'btc_dominance': str,
            'eth_dominance': str
        } or empty dict on error
    """
    try:
        global_data = fetch_global_metrics()
        
        if not global_data:
            return {}
        
        quote = global_data.get("quote", {}).get("USD", {})
        
        total_market_cap = safe_get(quote, "total_market_cap")
        total_volume = safe_get(quote, "total_volume_24h")
        market_cap_change = safe_get(quote, "total_market_cap_yesterday_percentage_change")
        
        btc_dominance = safe_get(global_data, "btc_dominance")
        eth_dominance = safe_get(global_data, "eth_dominance")
        
        return {
            "market_cap": format_number(total_market_cap),
            "volume": format_number(total_volume),
            "change": f"{market_cap_change:+.2f}%",
            "btc_dominance": f"{btc_dominance:.2f}%",
            "eth_dominance": f"{eth_dominance:.2f}%"
        }
        
    except Exception as e:
        print(f"[Global Data] Error: {e}")
        return {}
        
# ====== API CONFIGURATION ======
CMC_GLOBAL_API = "https://pro-api.coinmarketcap.com/v1/global-metrics/quotes/latest"
CMC_LISTINGS_API = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"
CMC_API_KEY = os.getenv("CMC_API_KEY")
FEAR_GREED_API = "https://api.alternative.me/fng/"

# ====== CACHING ======
CACHE_DURATION = 300  # 5 minutes in seconds
_global_market_cache = {
    "data": None,
    "timestamp": 0
}


# ====== UTILITY FUNCTIONS ======

def format_number(num: float) -> str:
    """
    Format large numbers with appropriate suffixes (T, B, M, K).
    
    Args:
        num: Number to format
    
    Returns:
        Formatted string with suffix
    """
    if num is None or num == 0:
        return "N/A"
    
    abs_num = abs(num)
    
    if abs_num >= 1_000_000_000_000:
        return f"${num / 1_000_000_000_000:.2f}T"
    elif abs_num >= 1_000_000_000:
        return f"${num / 1_000_000_000:.2f}B"
    elif abs_num >= 1_000_000:
        return f"${num / 1_000_000:.2f}M"
    elif abs_num >= 1_000:
        return f"${num / 1_000:.2f}K"
    else:
        return f"${num:,.2f}"


def get_fear_greed_emoji(value: int) -> str:
    """
    Get emoji based on Fear & Greed Index value.
    
    Args:
        value: Fear & Greed Index (0-100)
    
    Returns:
        Appropriate emoji
    """
    if value >= 75:
        return "🤑"  # Extreme Greed
    elif value >= 55:
        return "😊"  # Greed
    elif value >= 45:
        return "😐"  # Neutral
    elif value >= 25:
        return "😰"  # Fear
    else:
        return "😱"  # Extreme Fear


def get_trend_emoji(change_pct: float) -> str:
    """Get emoji for price change trend"""
    if change_pct > 5:
        return "🚀"
    elif change_pct > 0:
        return "📈"
    elif change_pct > -5:
        return "📉"
    else:
        return "💥"


def safe_get(data: dict, *keys, default=0):
    """
    Safely navigate nested dictionaries.
    
    Args:
        data: Dictionary to navigate
        *keys: Sequence of keys to follow
        default: Default value if key not found
    
    Returns:
        Value at nested key or default
    """
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key, default)
        else:
            return default
    return data if data is not None else default


# ====== API FETCHING ======

def fetch_global_metrics() -> Optional[Dict]:
    """
    Fetch global market metrics from CoinMarketCap.
    
    Returns:
        dict: Global metrics data or None if failed
    """
    if not CMC_API_KEY:
        print("⚠️ CMC_API_KEY not configured")
        return None
    
    try:
        headers = {
            "X-CMC_PRO_API_KEY": CMC_API_KEY,
            "Accept": "application/json"
        }
        
        response = requests.get(
            CMC_GLOBAL_API,
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        
        return response.json().get("data", {})
    
    except requests.Timeout:
        print("⚠️ CoinMarketCap API timeout")
        return None
    except requests.RequestException as e:
        print(f"⚠️ CoinMarketCap API error: {e}")
        return None
    except Exception as e:
        print(f"⚠️ Unexpected error fetching global metrics: {e}")
        return None


def fetch_top_movers(limit: int = 100) -> Tuple[Optional[Dict], Optional[Dict]]:
    """
    Fetch top gainer and loser from CoinMarketCap listings.
    
    Args:
        limit: Number of coins to analyze (default 100)
    
    Returns:
        tuple: (top_gainer, top_loser) or (None, None) if failed
    """
    if not CMC_API_KEY:
        return None, None
    
    try:
        headers = {
            "X-CMC_PRO_API_KEY": CMC_API_KEY,
            "Accept": "application/json"
        }
        
        response = requests.get(
            CMC_LISTINGS_API,
            headers=headers,
            params={
                "limit": limit,
                "sort": "market_cap",
                "convert": "USD"
            },
            timeout=10
        )
        response.raise_for_status()
        
        listings_data = response.json().get("data", [])
        
        if not listings_data:
            return None, None
        
        # Filter out stablecoins and get top movers
        filtered = [
            coin for coin in listings_data
            if coin.get("symbol") not in ["USDT", "USDC", "BUSD", "DAI", "TUSD", "USDD"]
        ]
        
        top_gainer = max(
            filtered,
            key=lambda x: safe_get(x, "quote", "USD", "percent_change_24h", default=-999),
            default=None
        )
        
        top_loser = min(
            filtered,
            key=lambda x: safe_get(x, "quote", "USD", "percent_change_24h", default=999),
            default=None
        )
        
        return top_gainer, top_loser
    
    except Exception as e:
        print(f"⚠️ Error fetching top movers: {e}")
        return None, None


def fetch_fear_greed() -> Tuple[Optional[str], Optional[str]]:
    """
    Fetch Fear & Greed Index from Alternative.me.
    
    Returns:
        tuple: (value, classification) or (None, None) if failed
    """
    try:
        response = requests.get(FEAR_GREED_API, timeout=5)
        response.raise_for_status()
        
        fng_data = response.json().get("data", [{}])[0]
        value = fng_data.get("value", "N/A")
        classification = fng_data.get("value_classification", "N/A")
        
        return value, classification
    
    except Exception as e:
        print(f"⚠️ Error fetching Fear & Greed Index: {e}")
        return None, None


# ====== MAIN FUNCTION ======

def get_global_market_message() -> str:
    """
    Fetch and format global crypto market data.
    Uses 5-minute caching to reduce API calls.
    
    Returns:
        str: Formatted market overview message
    """
    # Check cache first
    now = time.time()
    if (_global_market_cache["data"] and 
        now - _global_market_cache["timestamp"] < CACHE_DURATION):
        print("✅ Using cached global market data")
        return _global_market_cache["data"]
    
    try:
        # Fetch all data concurrently (in practice)
        global_data = fetch_global_metrics()
        top_gainer, top_loser = fetch_top_movers()
        fear_value, fear_classification = fetch_fear_greed()
        
        # Handle API failures gracefully
        if not global_data:
            return "⚠️ Could not fetch global market data. Please try again later."
        
        # Extract global metrics with safe fallbacks
        quote = global_data.get("quote", {}).get("USD", {})
        
        total_market_cap = safe_get(quote, "total_market_cap")
        total_volume = safe_get(quote, "total_volume_24h")
        market_cap_change = safe_get(quote, "total_market_cap_yesterday_percentage_change")
        
        btc_dominance = safe_get(global_data, "btc_dominance")
        eth_dominance = safe_get(global_data, "eth_dominance")
        
        defi_market_cap = safe_get(global_data, "defi_market_cap")
        defi_volume = safe_get(global_data, "defi_volume_24h")
        defi_dominance = safe_get(global_data, "defi_market_cap_dominance")
        
        stablecoin_market_cap = safe_get(global_data, "stablecoin_market_cap")
        stablecoin_volume = safe_get(global_data, "stablecoin_volume_24h")
        
        derivatives_volume = safe_get(global_data, "derivatives_volume_24h")
        
        # Calculate altcoin market cap
        altcoin_market_cap = total_market_cap * (
            (100 - btc_dominance - eth_dominance) / 100
        )
        
        # Get trend emoji
        trend_emoji = get_trend_emoji(market_cap_change)
        
        # Build message
        message_parts = [
            "🌍 *Global Crypto Market Overview*\n",
            
            "━━━━━━━━━━━━━━━━━━━━\n",
            "💰 *MARKET OVERVIEW*\n",
            f"Total Market Cap: {format_number(total_market_cap)}\n",
            f"24h Volume: {format_number(total_volume)}\n",
            f"24h Change: {market_cap_change:+.2f}% {trend_emoji}\n",
            
            "\n🏆 *DOMINANCE*\n",
            f"Bitcoin: {btc_dominance:.2f}%\n",
            f"Ethereum: {eth_dominance:.2f}%\n",
            f"Altcoins: {100 - btc_dominance - eth_dominance:.2f}%\n",
            f"Altcoin Market Cap: {format_number(altcoin_market_cap)}\n",
        ]
        
        # Add DeFi section if data available
        if defi_market_cap > 0:
            message_parts.extend([
                "\n⚙️ *DeFi ECOSYSTEM*\n",
                f"DeFi Market Cap: {format_number(defi_market_cap)}\n",
                f"DeFi Volume (24h): {format_number(defi_volume)}\n",
            ])
        
        # Add Stablecoin section if data available
        if stablecoin_market_cap > 0:
            message_parts.extend([
                "\n💵 *STABLECOINS*\n",
                f"Total Supply: {format_number(stablecoin_market_cap)}\n",
                f"24h Volume: {format_number(stablecoin_volume)}\n",
            ])
        
        # Add Derivatives section if data available
        if derivatives_volume > 0:
            message_parts.extend([
                "\n📊 *DERIVATIVES*\n",
                f"24h Volume: {format_number(derivatives_volume)}\n",
            ])
        
        # Add top movers if available
        if top_gainer and top_loser:
            gainer_name = top_gainer.get("name", "Unknown")
            gainer_symbol = top_gainer.get("symbol", "")
            gainer_change = safe_get(top_gainer, "quote", "USD", "percent_change_24h")
            
            loser_name = top_loser.get("name", "Unknown")
            loser_symbol = top_loser.get("symbol", "")
            loser_change = safe_get(top_loser, "quote", "USD", "percent_change_24h")
            
            message_parts.extend([
                "\n📈 *TOP MOVERS (24H)*\n",
                f"🚀 Top Gainer: {gainer_name} ({gainer_symbol}) {gainer_change:+.2f}%\n",
                f"📉 Top Loser: {loser_name} ({loser_symbol}) {loser_change:+.2f}%\n",
            ])
        
        # Add Fear & Greed Index if available
        if fear_value and fear_classification:
            try:
                fear_int = int(fear_value)
                fear_emoji = get_fear_greed_emoji(fear_int)
                message_parts.extend([
                    "\n😨 *FEAR & GREED INDEX*\n",
                    f"{fear_emoji} {fear_value}/100 - {fear_classification}\n",
                ])
            except ValueError:
                message_parts.extend([
                    "\n😨 *FEAR & GREED INDEX*\n",
                    f"{fear_value} - {fear_classification}\n",
                ])
        
        
        final_message = "".join(message_parts)
        
        # Cache the result
        _global_market_cache["data"] = final_message
        _global_market_cache["timestamp"] = now
        
        print("✅ Global market data fetched and cached")
        return final_message
    
    except Exception as e:
        print(f"⚠️ Unexpected error in get_global_market_message: {e}")
        return (
            "⚠️ An error occurred while fetching global market data.\n\n"
            "Please try again in a few moments."
        )


# ====== TELEGRAM COMMAND HANDLER ======

async def global_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /global command - show global crypto market overview.
    """
    user_id = update.effective_user.id
    
    # Track user activity
    await update_last_active(user_id, command_name="/global")
    await handle_streak(update, context)
    
    # Show loading message
    processing_msg = await update.message.reply_text(
        "⏳ Fetching global market data...",
        parse_mode="Markdown"
    )
    
    try:
        # Get market data
        message = get_global_market_message()
        
        # Update message with results
        await processing_msg.edit_text(message, parse_mode="Markdown")
    
    except Exception as e:
        print(f"⚠️ Error in global_command: {e}")
        await processing_msg.edit_text(
            "⚠️ Failed to fetch market data. Please try again.",
            parse_mode="Markdown"
        )


def clear_global_cache():
    """Manually clear the global market cache (useful for testing)"""
    global _global_market_cache
    _global_market_cache = {"data": None, "timestamp": 0}
    print("✅ Global market cache cleared")

def register_global_handler(app):
    """Register the /global command handler"""
    app.add_handler(CommandHandler("global", global_command))
    

# ====== TESTING ======
if __name__ == "__main__":
    # Test the message generation
    print("Testing global market message generation...")
    message = get_global_market_message()
    print("\n" + "="*50)
    print(message)
    print("="*50)
