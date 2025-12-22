# handlers/convert.py
import os
import json
import aiohttp
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from dotenv import load_dotenv
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

# Load .env
load_dotenv()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")

HEADERS = {"x-cg-demo-api-key": COINGECKO_API_KEY} if COINGECKO_API_KEY else {}

# Load CoinGecko IDs
base_dir = os.path.dirname(os.path.abspath(__file__))
ids_path = os.path.join(base_dir, "../utils/coingecko_ids.json")
with open(ids_path, "r") as f:
    COINGECKO_IDS = json.load(f)

COINGECKO_IDS = {k.upper(): v for k, v in COINGECKO_IDS.items()}

FIAT_CURRENCIES = {
    "USD", "EUR", "GBP", "NGN", "JPY", "CAD", "AUD", "INR",
    "CHF", "CNY", "HKD", "SGD", "SEK", "NOK", "DKK", "ZAR",
    "BRL", "MXN", "NZD", "RUB", "TRY", "AED", "SAR", "KES",
    "GHS", "EGP", "KRW", "TWD",
}

def format_num(n: float) -> str:
    if n == 0:
        return "0"
    if n < 0.01:
        return f"{n:.8f}".rstrip("0").rstrip(".")
    if n < 1:
        return f"{n:.6f}".rstrip("0").rstrip(".")
    return f"{n:,.2f}"


async def fetch_price(coin_id: str, vs: str):
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": coin_id, "vs_currencies": vs}

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(url, params=params, timeout=10) as r:
            if r.status != 200:
                return None
            data = await r.json()
            return data.get(coin_id, {}).get(vs)


async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/conv")
    await handle_streak(update, context)

    try:
        if len(context.args) != 4 or context.args[2].lower() != "to":
            return await update.message.reply_text(
                "❌ Usage:\n`/conv 2 eth to usd`\n`/conv 100 usd to btc`",
                parse_mode=ParseMode.MARKDOWN
            )

        amount = float(context.args[0])
        from_symbol = context.args[1].upper()
        to_symbol = context.args[3].upper()

        from_is_crypto = from_symbol in COINGECKO_IDS
        to_is_crypto = to_symbol in COINGECKO_IDS
        from_is_fiat = from_symbol in FIAT_CURRENCIES
        to_is_fiat = to_symbol in FIAT_CURRENCIES

        # 🔹 Crypto → Fiat
        if from_is_crypto and to_is_fiat:
            coin_id = COINGECKO_IDS[from_symbol]
            rate = await fetch_price(coin_id, to_symbol.lower())

            if rate is None:
                raise Exception("Rate fetch failed")

            converted = amount * rate
            text = (
                f"💱 *{format_num(amount)} {from_symbol}* = "
                f"*{format_num(converted)} {to_symbol}*\n"
                f"(1 {from_symbol} = {format_num(rate)} {to_symbol})"
            )

        # 🔹 Fiat → Crypto
        elif from_is_fiat and to_is_crypto:
            coin_id = COINGECKO_IDS[to_symbol]
            rate = await fetch_price(coin_id, from_symbol.lower())

            if rate is None:
                raise Exception("Rate fetch failed")

            converted = amount / rate
            text = (
                f"💱 *{format_num(amount)} {from_symbol}* = "
                f"*{format_num(converted)} {to_symbol}*\n"
                f"(1 {to_symbol} = {format_num(rate)} {from_symbol})"
            )

        else:
            return await update.message.reply_text(
                "❌ Only *Crypto ↔ Fiat* conversions are supported.\n\n"
                "Examples:\n"
                "`/conv 2 eth to usd`\n"
                "`/conv 100 usd to btc`",
                parse_mode=ParseMode.MARKDOWN
            )

        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    except ValueError:
        await update.message.reply_text(
            "❌ Invalid amount.\nExample: `/conv 2 eth to usd`",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        print("Convert Error:", e)
        await update.message.reply_text("⚠️ Conversion failed. Try again later.")