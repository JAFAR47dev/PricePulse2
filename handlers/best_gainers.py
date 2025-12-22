import os
import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ContextTypes
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

# Load environment variables
load_dotenv()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")
COINGECKO_API = "https://api.coingecko.com/api/v3"

async def get_top_gainers_message(per_page: int = 100) -> str:
    """Fetch top 3 gainers and return a formatted message."""
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
                price = c.get("current_price")
                change = c.get("price_change_percentage_24h")
                name = c.get("name") or "Unknown"
                symbol = (c.get("symbol") or "N/A").upper()

                if price is None or change is None:
                    continue

                safe_coins.append({
                    "name": name,
                    "symbol": symbol,
                    "price": price,
                    "change": change
                })
            except:
                continue

        top_gainers = sorted(safe_coins, key=lambda x: x["change"], reverse=True)[:3]

        if not top_gainers:
            return "❌ No gainers found."

        msg = f"🏆 *Top 3 Gainers (24h) — from Top {per_page} Coins*\n\n"

        for coin in top_gainers:
            msg += (
                f"• *{coin['name']}* ({coin['symbol']})\n"
                f"  Price: ${coin['price']:.4f}\n"
                f"  Gain: 📈 {coin['change']:.2f}%\n\n"
            )

        return msg

    except Exception as e:
        print(f"[Best] Error: {e}")
        return "❌ Could not fetch top gainers."
        
        
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

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
        "📈 *Choose coin range to scan gainers:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    
async def best_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    per_page = int(query.data.split("_")[1])

    loading_msg = await query.message.reply_text(f"📈 Scanning top {per_page} coins...")

    msg = await get_top_gainers_message(per_page)

    await loading_msg.edit_text(msg, parse_mode="Markdown")