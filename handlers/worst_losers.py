import os
import httpx
from telegram import Update
from telegram.ext import ContextTypes
from dotenv import load_dotenv
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

# Load .env file
load_dotenv()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")
COINGECKO_API = "https://api.coingecko.com/api/v3"


async def get_top_losers_message(per_page: int = 100) -> str:
    try:
        headers = {"accept": "application/json"}
        if COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": per_page,
            "page": 1,
            "price_change_percentage": "24h",
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0)) as client:
            response = await client.get(
                f"{COINGECKO_API}/coins/markets",
                params=params,
                headers=headers
            )

        response.raise_for_status()
        data = response.json()

        if not isinstance(data, list) or len(data) == 0:
            return "❌ No market data available right now."

        # Extract price change safely
        def safe_change(coin):
            return coin.get("price_change_percentage_24h") or 0

        losers = sorted(data, key=safe_change)[:3]

        msg = f"🔻 *Top 3 Losers (24h) — from Top {per_page} Coins*\n\n"

        for coin in losers:
            name = coin.get("name", "Unknown")
            symbol = coin.get("symbol", "?").upper()
            price = coin.get("current_price") or 0
            change = coin.get("price_change_percentage_24h") or 0

            msg += (
                f"• *{name}* ({symbol})\n"
                f"  Price: ${price:.4f}\n"
                f"  Loss: 🔻 {change:.2f}%\n\n"
            )

        return msg

    except Exception as e:
        print(f"Error worst losers: {e}")
        return "❌ Could not fetch top losers due to an API error."
        

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

async def worst_losers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/worst")
    await handle_streak(update, context)

    keyboard = [
        [
            InlineKeyboardButton("Top 50", callback_data="worst_50"),
            InlineKeyboardButton("Top 100", callback_data="worst_100"),
        ],
        [
            InlineKeyboardButton("Top 200", callback_data="worst_200"),
            InlineKeyboardButton("Top 500", callback_data="worst_500"),
        ]
    ]

    await update.message.reply_text(
        "📉 *Choose coin range to scan losers:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
async def worst_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    per_page = int(query.data.split("_")[1])

    loading_msg = await query.message.reply_text(f"📉 Scanning top {per_page} coins...")

    msg = await get_top_losers_message(per_page)

    await loading_msg.edit_text(msg, parse_mode="Markdown")
    
    