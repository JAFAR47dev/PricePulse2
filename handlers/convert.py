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
    """Fetch crypto price in specified currency (fiat or crypto)"""
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": coin_id, "vs_currencies": vs}

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(url, params=params, timeout=10) as r:
            if r.status != 200:
                return None
            data = await r.json()
            return data.get(coin_id, {}).get(vs)


async def fetch_exchange_rate(from_fiat: str, to_fiat: str):
    """Fetch fiat-to-fiat exchange rate using a crypto intermediary (USD)"""
    # Use BTC as intermediary to get fiat rates
    btc_id = "bitcoin"
    
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": btc_id, "vs_currencies": f"{from_fiat.lower()},{to_fiat.lower()}"}
        
        async with session.get(url, params=params, timeout=10) as r:
            if r.status != 200:
                return None
            data = await r.json()
            btc_data = data.get(btc_id, {})
            
            from_rate = btc_data.get(from_fiat.lower())
            to_rate = btc_data.get(to_fiat.lower())
            
            if from_rate and to_rate:
                # Convert via BTC: from_fiat -> BTC -> to_fiat
                return to_rate / from_rate
            return None


async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/conv")
    await handle_streak(update, context)

    try:
        if len(context.args) != 4 or context.args[2].lower() != "to":
            return await update.message.reply_text(
                "❌ Usage:\n"
                "`/conv 2 eth to usd` (Crypto → Fiat)\n"
                "`/conv 100 usd to btc` (Fiat → Crypto)\n"
                "`/conv 1 btc to eth` (Crypto → Crypto)\n"
                "`/conv 100 usd to eur` (Fiat → Fiat)",
                parse_mode=ParseMode.MARKDOWN
            )

        amount = float(context.args[0])
        from_symbol = context.args[1].upper()
        to_symbol = context.args[3].upper()

        from_is_crypto = from_symbol in COINGECKO_IDS
        to_is_crypto = to_symbol in COINGECKO_IDS
        from_is_fiat = from_symbol in FIAT_CURRENCIES
        to_is_fiat = to_symbol in FIAT_CURRENCIES

        # Validate input
        if not ((from_is_crypto or from_is_fiat) and (to_is_crypto or to_is_fiat)):
            return await update.message.reply_text(
                f"❌ Unsupported currency: *{from_symbol}* or *{to_symbol}*\n\n"
                "Please use valid crypto symbols (BTC, ETH, etc.) or fiat codes (USD, EUR, etc.)",
                parse_mode=ParseMode.MARKDOWN
            )

        # 🔹 Case 1: Crypto → Fiat
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

        # 🔹 Case 2: Fiat → Crypto
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

        # 🔹 Case 3: Crypto → Crypto
        elif from_is_crypto and to_is_crypto:
            from_coin_id = COINGECKO_IDS[from_symbol]
            to_coin_id = COINGECKO_IDS[to_symbol]
            
            # Get both prices in USD for comparison
            from_price_usd = await fetch_price(from_coin_id, "usd")
            to_price_usd = await fetch_price(to_coin_id, "usd")

            if from_price_usd is None or to_price_usd is None:
                raise Exception("Rate fetch failed")

            # Calculate cross rate
            rate = from_price_usd / to_price_usd
            converted = amount * rate
            
            text = (
                f"💱 *{format_num(amount)} {from_symbol}* = "
                f"*{format_num(converted)} {to_symbol}*\n"
                f"(1 {from_symbol} = {format_num(rate)} {to_symbol})"
            )

        # 🔹 Case 4: Fiat → Fiat
        elif from_is_fiat and to_is_fiat:
            rate = await fetch_exchange_rate(from_symbol, to_symbol)

            if rate is None:
                raise Exception("Rate fetch failed")

            converted = amount * rate
            text = (
                f"💱 *{format_num(amount)} {from_symbol}* = "
                f"*{format_num(converted)} {to_symbol}*\n"
                f"(1 {from_symbol} = {format_num(rate)} {to_symbol})"
            )

        else:
            return await update.message.reply_text(
                "❌ Invalid conversion pair.",
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