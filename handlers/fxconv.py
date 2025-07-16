# handlers/fxconv.py
import os
import requests
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from dotenv import load_dotenv

load_dotenv()
TWELVE_KEY = os.getenv("TWELVE_DATA_API_KEY")

def format_fx_pair(from_currency: str, to_currency: str) -> str:
    return f"{from_currency.upper()}/{to_currency.upper()}"

async def fxconv_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 4 or context.args[2].lower() != "to":
        return await update.message.reply_text("❌ Usage: /fxconv [amount] [from] to [to]\nExample: /fxconv 100 gbp to usd")

    try:
        amount = float(context.args[0])
        from_currency = context.args[1].upper()
        to_currency = context.args[3].upper()

        pair = format_fx_pair(from_currency, to_currency)

        url = "https://api.twelvedata.com/quote"
        params = {
            "symbol": pair,
            "apikey": TWELVE_KEY
        }

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        print("FX Conversion response:", data)

        if "code" in data or "close" not in data:
            msg = data.get("message", "No rate available.")
            return await update.message.reply_text(
                f"❌ Invalid or unsupported forex pair.\n\n_{msg}_",
                parse_mode=ParseMode.MARKDOWN
            )

        rate = float(data["close"])
        result = amount * rate

        text = (
            f"💱 *{amount:,.2f} {from_currency}* = *{result:,.2f} {to_currency}*\n"
            f"(1 {from_currency} = {rate:,.4f} {to_currency})"
        )

        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    except ValueError:
        await update.message.reply_text("❌ Invalid amount. Try a number like `100`.")
    except Exception as e:
        print("FXConv error:", e)
        await update.message.reply_text("⚠️ Failed to fetch conversion. Try again later.")