# handlers/compare.py
import requests
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

def format_num(n):
    return f"{n:,.2f}"

async def compare_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Expect format: /compare btc vs eth
        if len(context.args) != 3 or context.args[1].lower() != "vs":
            return await update.message.reply_text("❌ Usage: /compare [coin1] vs [coin2]")

        coin1 = context.args[0].lower()
        coin2 = context.args[2].lower()

        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "ids": f"{coin1},{coin2}"
        }

        r = requests.get(url, params=params)
        r.raise_for_status()
        data = r.json()

        if len(data) < 2:
            return await update.message.reply_text("❌ One or both coins are invalid or unsupported.")

        c1 = data[0] if data[0]["id"] == coin1 else data[1]
        c2 = data[1] if data[0]["id"] == coin1 else data[0]

        text = (
            f"🔍 *{c1['name']} vs {c2['name']}*\n\n"
            f"💵 Price:\n - {c1['symbol'].upper()}: *${format_num(c1['current_price'])}*\n - {c2['symbol'].upper()}: *${format_num(c2['current_price'])}*\n\n"
            f"📊 Market Cap:\n - {c1['symbol'].upper()}: *${format_num(c1['market_cap'])}*\n - {c2['symbol'].upper()}: *${format_num(c2['market_cap'])}*\n\n"
            f"📈 24h Volume:\n - {c1['symbol'].upper()}: *${format_num(c1['total_volume'])}*\n - {c2['symbol'].upper()}: *${format_num(c2['total_volume'])}*\n\n"
            f"📉 24h Change:\n - {c1['symbol'].upper()}: *{c1['price_change_percentage_24h']:.2f}%*\n - {c2['symbol'].upper()}: *{c2['price_change_percentage_24h']:.2f}%*\n"
        )

        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        print("Compare Error:", e)
        await update.message.reply_text("⚠️ Something went wrong. Please try again.")