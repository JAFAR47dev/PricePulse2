import os
import httpx
from telegram import Update
from telegram.ext import ContextTypes
from dotenv import load_dotenv
from tasks.handlers import handle_streak

# Load .env file
load_dotenv()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")
COINGECKO_API = "https://api.coingecko.com/api/v3"

# --- Reusable function for notifications ---
async def get_top_losers_message() -> str:
    """Fetch top 3 losers (biggest 24h drops) and return a formatted message string."""
    try:
        headers = {"accept": "application/json"}
        if COINGECKO_API_KEY:
            headers["x-cg-pro-api-key"] = COINGECKO_API_KEY

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{COINGECKO_API}/coins/markets",
                params={
                    "vs_currency": "usd",
                    "order": "market_cap_desc",
                    "per_page": 100,
                    "page": 1,
                    "price_change_percentage": "24h",
                },
                headers=headers,
                timeout=10
            )
            data = response.json()

        # Sort by lowest 24h % change → biggest losses
        top_losers = sorted(
            data,
            key=lambda x: x.get("price_change_percentage_24h", 0)
        )[:3]

        message = "🔻 *Top 3 Losers (24h)*:\n\n"
        for coin in top_losers:
            name = coin["name"]
            symbol = coin["symbol"].upper()
            price = coin["current_price"]
            change = coin["price_change_percentage_24h"]
            message += f"• *{name}* ({symbol})\n  Price: ${price:.2f}\n  Loss: 🔻 {change:.2f}%\n\n"

        return message

    except Exception as e:
        print(f"[Worst] Error fetching top losers: {e}")
        return "❌ Could not fetch top losers."


# --- Keep original command working ---
async def worst_losers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_streak(update, context)
    loading_msg = await update.message.reply_text("📉 Fetching top 24h losers...")
    message = await get_top_losers_message()
    await loading_msg.edit_text(message, parse_mode="Markdown")