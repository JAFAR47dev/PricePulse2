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


# =====================================================
# 🔥 Reliable API Caller: Top 3 Losers (24h)
# =====================================================
async def get_top_losers_message() -> str:
    """Fetch top 3 losers (24h) with strong reliability and fail-safes."""
    try:
        headers = {"accept": "application/json"}
        if COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 100,
            "page": 1,
            "price_change_percentage": "24h",
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0)) as client:
            response = await client.get(
                f"{COINGECKO_API}/coins/markets",
                params=params,
                headers=headers
            )

        # Raise if HTTP failure (429, 500, etc)
        response.raise_for_status()

        try:
            data = response.json()
        except ValueError:
            return "❌ API returned invalid data format."

        if not isinstance(data, list) or len(data) == 0:
            return "❌ No market data available right now."

        # Extract price changes safely
        def safe_change(coin):
            return coin.get("price_change_percentage_24h") or 0

        # Sort by lowest percentage → biggest losers
        losers = sorted(data, key=safe_change)[:3]

        msg = "🔻 *Top 3 Losers (24h)*:\n\n"

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

    except httpx.HTTPStatusError as e:
        print(f"[Worst] HTTP error: {e}")
        return "❌ API error: CoinGecko rate limit or server issue."

    except httpx.TimeoutException:
        print("[Worst] Timeout error.")
        return "⏳ Request timed out. Please try again."

    except Exception as e:
        print(f"[Worst] Unexpected error: {e}")
        return "❌ Could not fetch top losers due to an unexpected error."


# =====================================================
# 🚀 Command Handler (/worst)
# =====================================================
async def worst_losers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/worst")
    await handle_streak(update, context)

    loading_msg = await update.message.reply_text("📉 Fetching top 24h losers...")

    msg = await get_top_losers_message()

    await loading_msg.edit_text(msg, parse_mode="Markdown")