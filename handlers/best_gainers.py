from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters
)
import httpx
COINGECKO_API = "https://api.coingecko.com/api/v3"

async def best_gainers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Notify user it's working
        loading_msg = await update.message.reply_text("📈 Fetching top 24h gainers...")

        # Get top 100 coins by market cap
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

        await loading_msg.edit_text(message, parse_mode="Markdown")

    except Exception as e:
        print(f"Error in /best: {e}")
        await update.message.reply_text("❌ Could not fetch top gainers. Try again later.")   
     