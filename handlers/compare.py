from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from utils.prices import get_crypto_prices
import requests
import json
import os
from utils.formatting import format_large_number

# Load CoinGecko ID mappings
base_dir = os.path.dirname(os.path.abspath(__file__))
ids_path = os.path.join(base_dir, "../utils/coingecko_ids.json")
with open(ids_path, "r") as f:
    COINGECKO_IDS = json.load(f)

def format_num(n):
    return f"{n:,.2f}"

async def compare_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Require 2 or 3 coin symbols, no 'vs' needed
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

        # Step 1: Get live prices
        price_symbols = [f"{symbol}USDT" for symbol in coin_symbols]
        prices = await get_crypto_prices(price_symbols)

        # Step 2: Get CoinGecko market data
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "ids": ",".join(coin_ids)
        }
        r = requests.get(url, params=params)
        r.raise_for_status()
        data = r.json()

        # Verify all coins are present
        if len(data) < len(coin_ids):
            return await update.message.reply_text("❌ One or more coins are invalid or unavailable.")

        # Match data by ID
        coin_data = {d['id']: d for d in data}

        # Step 3: Construct side-by-side table
        def row(title, attr, fmt=lambda x: x):
            values = []
            for i, symbol in enumerate(coin_symbols):
                coin_id = coin_ids[i]
                if attr == "price":
                    value = prices.get(f"{symbol}USDT")
                    values.append(f"${format_num(value)}" if value else "N/A")
                else:
                    raw = coin_data[coin_id].get(attr)
                    if attr == "price_change_percentage_24h" and raw is not None:
                        values.append(f"{raw:.2f}%")
                    elif raw is not None:
                        values.append(f"${format_num(raw)}")
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