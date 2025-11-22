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

        # Safety: remove coins without 24h change or price
        safe_coins = []
        for c in data:
            try:
                price = c.get("current_price")
                change = c.get("price_change_percentage_24h")
                name = c.get("name") or "Unknown"
                symbol = (c.get("symbol") or "N/A").upper()

                # Skip coins with missing price
                if price is None or change is None:
                    continue

                safe_coins.append({
                    "name": name,
                    "symbol": symbol,
                    "price": price,
                    "change": change
                })
            except Exception:
                continue  # skip any problematic coin

        # Sort by highest 24h % gain
        top_gainers = sorted(safe_coins, key=lambda x: x["change"], reverse=True)[:3]

        if not top_gainers:
            return "❌ No gainers found."

        message = "🏆 *Top 3 Gainers (24h)*:\n\n"
        for coin in top_gainers:
            message += (
                f"• *{coin['name']}* ({coin['symbol']})\n"
                f"  Price: ${coin['price']:.2f}\n"
                f"  Gain: 📈 {coin['change']:.2f}%\n\n"
            )

        return message

    except Exception as e:
        print(f"[Best] Error fetching top gainers: {e}")
        return "❌ Could not fetch top gainers."


async def best_gainers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        await update_last_active(user_id)
        await handle_streak(update, context)
        loading_msg = await update.message.reply_text("📈 Fetching top 24h gainers...")
        message = await get_top_gainers_message()
        await loading_msg.edit_text(message, parse_mode="Markdown")
    except Exception as e:
        print(f"[Best Command] Error: {e}")
        await update.message.reply_text("⚠️ Something went wrong while fetching top gainers.")