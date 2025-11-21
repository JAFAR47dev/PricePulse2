# handlers/convert.py
import os
import json
import requests
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from dotenv import load_dotenv
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

# Load your symbol-to-ID mappings
base_dir = os.path.dirname(os.path.abspath(__file__))
ids_path = os.path.join(base_dir, "../utils/coingecko_ids.json")
with open(ids_path, "r") as f:
    COINGECKO_IDS = json.load(f)

# Lowercase the keys for consistency
COINGECKO_IDS = {k.upper(): v for k, v in COINGECKO_IDS.items()}

# Some common fiat currencies
FIAT_CURRENCIES = {"usd", "eur", "gbp", "ngn", "jpy", "cad", "aud", "inr"}

def format_num(n):
    """Format number dynamically: 2 decimals for large, up to 8 for small values."""
    if n == 0:
        return "0"
    elif n < 0.01:
        return f"{n:.8f}".rstrip("0").rstrip(".")
    elif n < 1:
        return f"{n:.6f}".rstrip("0").rstrip(".")
    else:
        return f"{n:,.2f}"


# Load .env variables
load_dotenv()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")

# ✅ Header for authenticated requests
HEADERS = {"x-cg-demo-api-key": COINGECKO_API_KEY} if COINGECKO_API_KEY else {}


async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id)
    await handle_streak(update, context)
    try:
        if len(context.args) != 4 or context.args[2].lower() != "to":
            return await update.message.reply_text("❌ Usage: /conv [amount] [coin] to [fiat]")

        amount = float(context.args[0])
        from_symbol = context.args[1].upper()
        to_symbol = context.args[3].upper()

        from_is_crypto = from_symbol in COINGECKO_IDS
        to_is_crypto = to_symbol in COINGECKO_IDS

        # --- Crypto → Fiat ---
        if from_is_crypto and to_symbol.lower() in FIAT_CURRENCIES:
            coin_id = COINGECKO_IDS[from_symbol]
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {"ids": coin_id, "vs_currencies": to_symbol.lower()}

            r = requests.get(url, params=params, headers=HEADERS, timeout=10)
            data = r.json()

            if coin_id not in data or to_symbol.lower() not in data[coin_id]:
                return await update.message.reply_text("❌ Conversion failed. Coin or currency not supported.")

            rate = data[coin_id][to_symbol.lower()]
            converted = amount * rate
            text = (
                f"💱 *{format_num(amount)} {from_symbol}* = *{format_num(converted)} {to_symbol}*\n"
                f"(1 {from_symbol} = {format_num(rate)} {to_symbol})"
            )

        # --- Fiat → Crypto ---
        elif to_is_crypto and from_symbol.lower() in FIAT_CURRENCIES:
            coin_id = COINGECKO_IDS[to_symbol]
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {"ids": coin_id, "vs_currencies": from_symbol.lower()}

            r = requests.get(url, params=params, headers=HEADERS, timeout=10)
            data = r.json()

            if coin_id not in data or from_symbol.lower() not in data[coin_id]:
                return await update.message.reply_text("❌ Conversion failed. Coin or currency not supported.")

            rate = data[coin_id][from_symbol.lower()]
            converted = amount / rate
            text = (
                f"💱 *{format_num(amount)} {from_symbol}* = *{format_num(converted)} {to_symbol}*\n"
                f"(1 {to_symbol} = {format_num(rate)} {from_symbol})"
            )

        # --- Crypto → Crypto or invalid ---
        else:
            return await update.message.reply_text(
                "❌ Currently only supports Crypto ↔ Fiat conversions.\nTry:\n`/conv 2 eth to usd`\n`/conv 100 usd to btc`",
                parse_mode=ParseMode.MARKDOWN
            )

        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    except ValueError:
        await update.message.reply_text("❌ Invalid amount. Try something like `/conv 2 eth to usd`")
    except Exception as e:
        print("Convert Error:", e)
        await update.message.reply_text("⚠️ Failed to fetch conversion. Try again later.")