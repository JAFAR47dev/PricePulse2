import os
import requests
from dotenv import load_dotenv
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

load_dotenv()
BLOCKNATIVE_API_KEY = os.getenv("BLOCKNATIVE_API_KEY")  # Ensure it's set in your .env

# --- Reusable function for notifications ---
def get_gas_fees() -> str:
    """Fetch Ethereum gas fees and return a formatted string."""
    try:
        url = "https://api.blocknative.com/gasprices/blockprices"
        headers = {
            "Authorization": BLOCKNATIVE_API_KEY,
            "Accept": "application/json"
        }

        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()

        blocks = data.get("blockPrices")
        if not blocks or not isinstance(blocks, list):
            raise Exception("Unexpected Blocknative response")

        block = blocks[0]
        estimated_prices = block.get("estimatedPrices", [])
        if not estimated_prices:
            raise Exception("No gas data available")

        # Sort by confidence (descending)
        estimated_prices.sort(key=lambda x: x["confidence"], reverse=True)

        low = estimated_prices[-1]["price"] if len(estimated_prices) > 2 else estimated_prices[-1]["price"]
        avg = estimated_prices[len(estimated_prices)//2]["price"]
        high = estimated_prices[0]["price"]
        block_number = block.get("blockNumber", "N/A")

        text = (
            f"⛽ *Ethereum Gas Fees (Blocknative)*\n\n"
            f"• Low: `{low:.1f}` Gwei (safe, slower)\n"
            f"• Standard: `{avg:.1f}` Gwei (balanced)\n"
            f"• High: `{high:.1f}` Gwei (fast)\n\n"
            f"🧱 Latest Block: `{block_number}`\n"
            f"🔍 _Powered by Blocknative_"
        )
        return text

    except Exception as e:
        print("[Gas Fees] Error:", e)
        return "⚠️ Couldn't fetch gas fees. Try again later."


# --- Keep the original Telegram command working ---
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

async def gasfees_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/gas")
    await handle_streak(update, context)
    text = get_gas_fees()
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)