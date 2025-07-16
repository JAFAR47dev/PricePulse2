# handlers/daily_coin.py
import requests
import datetime
import os
import json
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

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

async def coin_of_the_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        symbol, coin_id = get_daily_symbol()

        # Fetch price & market data
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        coin_name = data["name"]
        price = data["market_data"]["current_price"]["usd"]
        change = data["market_data"]["price_change_percentage_24h"]
        market_cap = data["market_data"]["market_cap"]["usd"]
        desc = data["description"]["en"].split(".")[0][:160]  # One-line summary

        text = (
            f"🪙 *Coin of the Day: {coin_name} ({symbol})*\n\n"
            f"💵 Price: ${price:,.2f}\n"
            f"📊 24h Change: {change:+.2f}%\n"
            f"📈 Market Cap: ${market_cap / 1e9:.2f}B\n"
            f"🔍 Use Case: {desc or 'No description found.'}\n\n"
            f"✨ Want full charts, Pro tips & alerts?\n"
            f"👉 /upgrade"
        )

        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        print("Coin of the Day error:", e)
        await update.message.reply_text("⚠️ Couldn't fetch Coin of the Day. Try again later.")