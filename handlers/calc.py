import os, json, requests
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from dotenv import load_dotenv
from tasks.handlers import handle_streak
# Load environment variables
load_dotenv()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")

# Load symbol-to-ID mapping
base_dir = os.path.dirname(os.path.abspath(__file__))
ids_path = os.path.join(base_dir, "../utils/coingecko_ids.json")
with open(ids_path, "r") as f:
    COINGECKO_IDS = json.load(f)
COINGECKO_IDS = {k.upper(): v for k, v in COINGECKO_IDS.items()}

# Supported fiat currencies
FIAT_CURRENCIES = {"USD", "EUR", "GBP", "NGN", "JPY", "CAD", "AUD", "INR"}

def format_num(n):
    try:
        return f"{float(n):,.2f}"
    except:
        return n

async def calc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_streak(update, context)
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /calc [amount] [coin/fiat]\nExample: /calc 100 btc or /calc 30000 gbp")
        return

    amount, symbol = context.args
    amount = float(amount)
    symbol = symbol.upper()

    headers = {}
    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

    # ===============================
    # CASE 1: Fiat currency
    # ===============================
    if symbol in FIAT_CURRENCIES:
        url = "https://api.coingecko.com/api/v3/exchange_rates"
        data = requests.get(url, headers=headers, timeout=10).json()
        rates = data.get("rates", {})

        fiat_rate = rates.get(symbol.lower(), {}).get("value")
        usd_rate = rates.get("usd", {}).get("value", 1)

        if fiat_rate:
            # Convert fiat → USD
            usd_value = (amount / fiat_rate) * usd_rate
            usd_per_unit = (1 / fiat_rate) * usd_rate

            msg = (
                f"💱 *{symbol} to USD*\n\n"
                f"• 1 {symbol} = ${format_num(usd_per_unit)} USD\n"
                f"• {format_num(amount)} {symbol} = ${format_num(usd_value)} USD"
            )
            await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            await update.message.reply_text(f"⚠️ Couldn't find rate for {symbol}")
        return

    # ===============================
    # CASE 2: Cryptocurrency
    # ===============================
    if symbol in COINGECKO_IDS:
        coin_id = COINGECKO_IDS[symbol]
        url = f"https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": coin_id, "vs_currencies": "usd"}
        resp = requests.get(url, headers=headers, params=params, timeout=10).json()
        price = resp.get(coin_id, {}).get("usd")

        if price:
            total = price * amount
            msg = (
                f"💰 *{symbol} Price*\n\n"
                f"• 1 {symbol} = ${format_num(price)} USD\n"
                f"• {format_num(amount)} {symbol} = ${format_num(total)} USD"
            )
            await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ Couldn't fetch coin price right now.")
    else:
        await update.message.reply_text(f"❌ Unknown symbol '{symbol}'.")