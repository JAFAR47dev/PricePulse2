import requests
import datetime
import os
import json
from dotenv import load_dotenv
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

load_dotenv()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")

# --- Helper to select today's coin ---
def get_daily_symbol():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    ids_path = os.path.join(base_dir, "../utils/coingecko_ids.json")

    with open(ids_path) as f:
        symbol_to_id = json.load(f)

    sorted_symbols = sorted(symbol_to_id.keys())
    index = datetime.datetime.utcnow().timetuple().tm_yday % len(sorted_symbols)
    symbol = sorted_symbols[index]
    coin_id = symbol_to_id[symbol]

    return symbol, coin_id
    
def safe_fetch_coin(coin_id, headers):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[Coin of the Day] Error fetching {coin_id}:", e)
        return None


def get_coin_of_the_day() -> str:
    """Fetch Coin of the Day info and return a formatted string."""
    try:
        symbol, coin_id = get_daily_symbol()

        headers = {"accept": "application/json"}
        if COINGECKO_API_KEY:
            headers["x-cg-pro-api-key"] = COINGECKO_API_KEY

        data = safe_fetch_coin(coin_id, headers)
        if not data:
            return f"⚠️ Coin of the Day unavailable — CoinGecko does not support '{coin_id}'."

        coin_name = data["name"]
        price = data["market_data"]["current_price"]["usd"]
        change = data["market_data"]["price_change_percentage_24h"]
        market_cap = data["market_data"]["market_cap"]["usd"]
        desc = data["description"]["en"].split(".")[0][:160] if data["description"]["en"] else "No description available."

        text = (
            f"🪙 *Coin of the Day: {coin_name} ({symbol})*\n\n"
            f"💵 Price: ${price:,.2f}\n"
            f"📊 24h Change: {change:+.2f}%\n"
            f"📈 Market Cap: ${market_cap / 1e9:.2f}B\n"
            f"🔍 Use Case: {desc}\n\n"
            f"✨ Want full charts, portfolio tracking & alerts?\n"
            f"👉 /upgrade"
        )
        return text

    except Exception as e:
        print("[Coin of the Day] Error:", e)
        return "⚠️ Couldn't fetch Coin of the Day. Try again later."
        

# --- Keep original Telegram command ---
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

async def coin_of_the_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id)
    await handle_streak(update, context)
    text = get_coin_of_the_day()
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)