from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler
import httpx

COINGECKO_API = "https://api.coingecko.com/api/v3"


async def worst_losers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        loading_msg = await update.message.reply_text("📉 Fetching top 24h losers...")

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
                timeout=10
            )
            data = response.json()

        # Sort by lowest 24h % gain (i.e., biggest losses)
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

        await loading_msg.edit_text(message, parse_mode="Markdown")

    except Exception as e:
        print(f"Error in /worst: {e}")
        await update.message.reply_text("❌ Could not fetch losers. Try again later.") 