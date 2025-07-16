# handlers/convert.py
import requests
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Check argument count
        if len(context.args) != 4 or context.args[2].lower() != "to":
            return await update.message.reply_text("❌ Usage: /convert [amount] [coin] to [currency]")

        amount = float(context.args[0])
        from_coin = context.args[1].lower()
        to_currency = context.args[3].lower()

        # API call to CoinGecko
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": from_coin,
            "vs_currencies": to_currency
        }

        response = requests.get(url, params=params)
        data = response.json()

        if from_coin not in data or to_currency not in data[from_coin]:
            return await update.message.reply_text("❌ Invalid coin or currency.")

        rate = data[from_coin][to_currency]
        converted = amount * rate

        text = (
            f"💱 *{amount} {from_coin.upper()}* = *{converted:,.2f} {to_currency.upper()}*\n"
            f"(1 {from_coin.upper()} = {rate:,.2f} {to_currency.upper()})"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    except ValueError:
        await update.message.reply_text("❌ Invalid amount. Try something like `/convert 2 eth to usd`")
    except Exception as e:
        print("Convert Error:", e)
        await update.message.reply_text("⚠️ Failed to fetch conversion. Try again later.")