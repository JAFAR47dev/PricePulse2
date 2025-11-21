from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from utils.prices import get_crypto_prices
from utils.formatting import format_large_number
import requests
import json
import os
from dotenv import load_dotenv
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

# Load environment variables
load_dotenv()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")

# Load CoinGecko ID mappings
base_dir = os.path.dirname(os.path.abspath(__file__))
ids_path = os.path.join(base_dir, "../utils/coingecko_ids.json")
with open(ids_path, "r") as f:
    COINGECKO_IDS = json.load(f)

async def compare_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id)
    await handle_streak(update, context)
    try:
        args = context.args
        if len(args) < 2 or len(args) > 3:
            return await update.message.reply_text("❌ Usage: /comp [coin1] [coin2] [optional coin3]")

        # Prepare symbols and CoinGecko IDs
        coin_symbols = [arg.upper() for arg in args]
        coin_ids = []
        for symbol in coin_symbols:
            coin_id = COINGECKO_IDS.get(symbol)
            if not coin_id:
                return await update.message.reply_text(f"❌ Unsupported symbol: {symbol}")
            coin_ids.append(coin_id)

        # Step 1: Get live prices via your price fetcher
        price_symbols = [f"{symbol}USDT" for symbol in coin_symbols]
        prices = await get_crypto_prices(price_symbols)

        # Step 2: Get CoinGecko market data (with API key)
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "ids": ",".join(coin_ids),
        }

        headers = {}
        if COINGECKO_API_KEY:
            headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

        r = requests.get(url, params=params, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()

        if len(data) < len(coin_ids):
            return await update.message.reply_text("❌ One or more coins are invalid or unavailable.")

        # Map data by ID
        coin_data = {d["id"]: d for d in data}

        # Step 3: Build comparison table
        def row(title, attr):
            values = []
            for i, symbol in enumerate(coin_symbols):
                coin_id = coin_ids[i]
                if attr == "price":
                    value = prices.get(f"{symbol}USDT")
                    values.append(f"${format_large_number(value)}" if value else "N/A")
                else:
                    raw = coin_data[coin_id].get(attr)
                    if attr == "price_change_percentage_24h" and raw is not None:
                        values.append(f"{raw:.2f}%")
                    elif raw is not None:
                        values.append(f"${format_large_number(raw)}")
                    else:
                        values.append("N/A")
            return f"*{title}:*  " + " | ".join(values)

        text = (
            f"🔍 *Comparing:* {' | '.join(coin_symbols)}\n\n"
            f"{row('💵 Price', 'price')}\n"
            f"{row('📊 Market Cap', 'market_cap')}\n"
            f"{row('📈 24h Volume', 'total_volume')}\n"
            f"{row('📉 24h Change', 'price_change_percentage_24h')}"
        )

        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        print("Compare Error:", e)
        await update.message.reply_text("⚠️ Something went wrong. Please try again.")