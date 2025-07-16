# handlers/daily_coin.py
import requests
import datetime
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

def get_daily_coin_index():
    # Rotates daily based on day of year
    return datetime.datetime.utcnow().timetuple().tm_yday % 100  # Index 0–99

def load_top_100_coins():
    import json
    with open("utils/top_100_coins.json") as f:
        return json.load(f)

async def coin_of_the_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        top_100 = load_top_100_coins()
        coin = top_100[get_daily_coin_index()]  # Rotate daily

        coin_id = coin["id"]
        coin_symbol = coin["symbol"].upper()
        coin_name = coin["name"]

        # Fetch price & market data
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        price = data["market_data"]["current_price"]["usd"]
        change = data["market_data"]["price_change_percentage_24h"]
        market_cap = data["market_data"]["market_cap"]["usd"]
        desc = data["description"]["en"].split(".")[0][:160]  # One-line description

        text = (
            f"🪙 *Coin of the Day: {coin_name} ({coin_symbol})*\n\n"
            f"💵 Price: ${price:,.2f}\n"
            f"📊 24h Change: {change:+.2f}%\n"
            f"📈 Market Cap: ${market_cap/1e9:.2f}B\n"
            f"🔍 Use Case: {desc or 'No description found.'}\n\n"
            f"✨ Want full charts, Pro tips & alerts?\n"
            f"👉 /upgrade"
        )

        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        await update.message.reply_text("⚠️ Couldn't fetch Coin of the Day. Try again later.")