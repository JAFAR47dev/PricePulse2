# handlers/best.py

import os
import httpx
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

load_dotenv()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")
COINGECKO_API = "https://api.coingecko.com/api/v3"


# ============================================================================
# DATA FUNCTION (for notifications)
# ============================================================================

async def get_top_gainers_data(per_page: int = 100) -> list:
    """
    Fetch top 3 gainers and return raw data as list of tuples.
    
    Returns:
        list: [(coin_name, change_percent), ...] or empty list on error
    """
    try:
        headers = {}
        if COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": per_page,
            "page": 1,
            "price_change_percentage": "24h",
        }

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{COINGECKO_API}/coins/markets",
                params=params,
                headers=headers
            )

        response.raise_for_status()
        data = response.json()

        safe_coins = []
        for c in data:
            try:
                change = c.get("price_change_percentage_24h")
                name = c.get("name") or "Unknown"
                symbol = (c.get("symbol") or "N/A").upper()

                if change is None:
                    continue

                safe_coins.append({
                    "name": name,
                    "symbol": symbol,
                    "change": change
                })
            except:
                continue

        top_gainers = sorted(safe_coins, key=lambda x: x["change"], reverse=True)[:3]

        # Return as list of tuples: [(name, change_str), ...]
        return [(f"{c['name']} ({c['symbol']})", f"+{c['change']:.2f}%") for c in top_gainers]

    except Exception as e:
        print(f"[Best] Error: {e}")
        return []


# ============================================================================
# MESSAGE FUNCTION WITH MOMENTUM (ENHANCED)
# ============================================================================

async def get_top_gainers_message(per_page: int = 100) -> str:
    """Fetch top 3 gainers with momentum indicators and return formatted message."""
    try:
        headers = {}
        if COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

        # Request both 1h and 24h price changes
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": per_page,
            "page": 1,
            "price_change_percentage": "1h,24h",  # Request both timeframes
        }

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{COINGECKO_API}/coins/markets",
                params=params,
                headers=headers
            )

        response.raise_for_status()
        data = response.json()

        safe_coins = []
        for c in data:
            try:
                price = c.get("current_price")
                change_24h = c.get("price_change_percentage_24h")
                change_1h = c.get("price_change_percentage_1h_in_currency")
                volume = c.get("total_volume", 0)
                market_cap = c.get("market_cap", 1)
                name = c.get("name") or "Unknown"
                symbol = (c.get("symbol") or "N/A").upper()

                if price is None or change_24h is None:
                    continue

                # Calculate volume/market cap ratio
                volume_ratio = (volume / market_cap * 100) if market_cap > 0 else 0

                safe_coins.append({
                    "name": name,
                    "symbol": symbol,
                    "price": price,
                    "change_24h": change_24h,
                    "change_1h": change_1h if change_1h is not None else 0,
                    "volume": volume,
                    "volume_ratio": volume_ratio
                })
            except Exception as e:
                print(f"Error processing coin: {e}")
                continue

        top_gainers = sorted(safe_coins, key=lambda x: x["change_24h"], reverse=True)[:3]

        if not top_gainers:
            return "❌ No gainers found."

        msg = f"🏆 **Top 3 Gainers (24h)** — Top {per_page} Coins\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        for i, coin in enumerate(top_gainers, 1):
            # Determine momentum status
            momentum = get_momentum_indicator(coin["change_1h"], coin["change_24h"])
            volume_indicator = get_volume_indicator(coin["volume_ratio"])
            
            msg += (
                f"{i}. **{coin['name']}** ({coin['symbol']})\n"
                f"   💵 Price: `${coin['price']:,.4f}`\n"
                f"   📈 24h: `+{coin['change_24h']:.2f}%`\n"
                f"   {momentum['emoji']} Momentum: **{momentum['status']}** ({coin['change_1h']:+.1f}% last hour)\n"
                f"   {volume_indicator['emoji']} Volume: {volume_indicator['status']}\n\n"
            )

       

        return msg

    except Exception as e:
        print(f"[Best] Error: {e}")
        return "❌ Could not fetch top gainers."


def get_momentum_indicator(change_1h: float, change_24h: float) -> dict:
    """
    Determine momentum status based on 1h vs 24h changes
    
    Returns:
        dict with 'emoji' and 'status' keys
    """
    # Strong momentum: still gaining significantly
    if change_1h > 3:
        return {"emoji": "🔥", "status": "STRONG"}
    
    # Good momentum: positive and steady
    elif change_1h > 1:
        return {"emoji": "✅", "status": "GOOD"}
    
    # Slowing: positive but losing steam
    elif 0 < change_1h <= 1:
        return {"emoji": "🟡", "status": "SLOWING"}
    
    # Cooling: flat or slightly negative
    elif -1 <= change_1h <= 0:
        return {"emoji": "🟠", "status": "COOLING"}
    
    # Reversing: actively dropping
    else:  # change_1h < -1
        return {"emoji": "🔴", "status": "REVERSING"}


def get_volume_indicator(volume_ratio: float) -> dict:
    """
    Determine volume status based on volume/market cap ratio
    
    Returns:
        dict with 'emoji' and 'status' keys
    """
    if volume_ratio > 20:
        return {"emoji": "🔊", "status": "Very High"}
    elif volume_ratio > 10:
        return {"emoji": "📢", "status": "High"}
    elif volume_ratio > 5:
        return {"emoji": "🔔", "status": "Medium"}
    else:
        return {"emoji": "🔕", "status": "Low"}


# ============================================================================
# TELEGRAM COMMAND HANDLERS
# ============================================================================

async def best_gainers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/best")
    await handle_streak(update, context)

    keyboard = [
        [
            InlineKeyboardButton("Top 50", callback_data="best_50"),
            InlineKeyboardButton("Top 100", callback_data="best_100"),
        ],
        [
            InlineKeyboardButton("Top 200", callback_data="best_200"),
        ]
    ]

    await update.message.reply_text(
        "📈 **Choose coin range to scan gainers:**",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def best_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    per_page = int(query.data.split("_")[1])

    loading_msg = await query.message.reply_text(
        f"📈 Scanning top {per_page} coins...\n⏱️ Analyzing momentum...",
        parse_mode=ParseMode.MARKDOWN
    )

    msg = await get_top_gainers_message(per_page)

    await loading_msg.edit_text(msg, parse_mode=ParseMode.MARKDOWN)

