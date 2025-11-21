# handlers/fx.py
import os
import requests
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from dotenv import load_dotenv
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

load_dotenv()
TWELVE_KEY = os.getenv("TWELVE_DATA_API_KEY")

# Common forex pairs (auto-convert to API format with slash)
COMMON_PAIRS = [
    "EUR/USD", "USD/JPY", "GBP/USD", "USD/CHF", "AUD/USD",
    "USD/CAD", "NZD/USD", "EUR/JPY", "GBP/JPY", "EUR/GBP",
    "USD/ZAR", "USD/NGN", "USD/CNY"
]

DEFAULT_QUOTE = "USD"
DEFAULT_BASE = "EUR"

def format_pair(user_input: str) -> str | None:
    user_input = user_input.upper().replace("/", "")

    if len(user_input) == 6:
        base = user_input[:3]
        quote = user_input[3:]
        return f"{base}/{quote}"

    elif len(user_input) == 3:
        if user_input == DEFAULT_QUOTE:
            return f"{DEFAULT_BASE}/{user_input}"
        else:
            return f"{user_input}/{DEFAULT_QUOTE}"

    return None

async def fx_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id)
    await handle_streak(update, context)
    if len(context.args) != 1:
        return await update.message.reply_text("❌ Usage: /fx [pair]\nExample: /fx eurusd or /fx usd")

    raw = context.args[0]
    pair = format_pair(raw)

    if not pair:
        return await update.message.reply_text("❌ Invalid forex pair. Try /fx eurusd or /fx jpy")

    try:
        # Quote endpoint
        url = "https://api.twelvedata.com/quote"
        params = {
            "symbol": pair,
            "apikey": TWELVE_KEY
        }

        r = requests.get(url, params=params, timeout=10)
        data = r.json()


        # Error handling
        if "code" in data or "close" not in data:
            msg = data.get("message", "No rate available.")
            return await update.message.reply_text(
                f"❌ Invalid or unsupported forex pair.\n\n_{msg}_",
                parse_mode=ParseMode.MARKDOWN
            )

        price = float(data["close"])
        high_24h = float(data.get("high", 0))
        low_24h = float(data.get("low", 0))
        change_pct = float(data.get("percent_change", 0))

        # Weekly high/low
        try:
            hist_url = "https://api.twelvedata.com/time_series"
            hist_params = {
                "symbol": pair,
                "interval": "1day",
                "outputsize": 7,
                "apikey": TWELVE_KEY
            }

            hist_res = requests.get(hist_url, params=hist_params, timeout=10)
            hist_data = hist_res.json()
            candles = hist_data.get("values", [])

            if candles:
                week_high = max(float(c["high"]) for c in candles)
                week_low = min(float(c["low"]) for c in candles)
            else:
                week_high = week_low = None

        except Exception as e:
            print("Weekly high/low fetch failed:", e)
            week_high = week_low = None

        # Final response text
        text = (
            f"📊 *Forex Pair: {pair}*\n\n"
            f"💵 Rate: {price:,.4f}\n"
            f"📈 24h High: {high_24h:,.4f} | 📉 24h Low: {low_24h:,.4f}\n"
        )

        if week_high and week_low:
            text += f"📅 Weekly High: {week_high:,.4f} | Weekly Low: {week_low:,.4f}\n"

        text += f"📊 24h Change: {change_pct:+.2f}%"

        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        print("FX command error:", e)
        await update.message.reply_text("⚠️ Failed to fetch forex data. Try again later.")