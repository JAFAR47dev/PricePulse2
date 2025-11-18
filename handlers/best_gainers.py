import os
import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ContextTypes
from tasks.handlers import handle_streak

# Load environment variables
load_dotenv()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")
COINGECKO_API = "https://api.coingecko.com/api/v3"

# --- NEW: Reusable function for notifications ---
async def get_top_gainers_message() -> str:
    """Fetch top 3 gainers and return a formatted message string."""
    try:
        headers = {}
        if COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

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
            response.raise_for_status()
            data = response.json()

        # Sort by highest 24h % gain
        top_gainers = sorted(
            data,
            key=lambda x: x.get("price_change_percentage_24h", 0),
            reverse=True
        )[:3]

        message = "🏆 *Top 3 Gainers (24h)*:\n\n"
        for coin in top_gainers:
            name = coin["name"]
            symbol = coin["symbol"].upper()
            price = coin["current_price"]
            change = coin["price_change_percentage_24h"]
            message += f"• *{name}* ({symbol})\n  Price: ${price:.2f}\n  Gain: 📈 {change:.2f}%\n\n"

        return message

    except Exception as e:
        print(f"[Best] Error fetching top gainers: {e}")
        return "❌ Could not fetch top gainers."


# --- Keep original command working ---
async def best_gainers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_streak(update, context)
    loading_msg = await update.message.reply_text("📈 Fetching top 24h gainers...")
    message = await get_top_gainers_message()
    await loading_msg.edit_text(message, parse_mode="Markdown")