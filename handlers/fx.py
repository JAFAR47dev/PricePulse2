# handlers/fx.py
import os
import requests
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from dotenv import load_dotenv
from tasks.handlers import handle_streak
from models.user_activity import update_last_active
from datetime import datetime

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

def calculate_volatility(candles):
    """Calculate price volatility from candle data"""
    if not candles or len(candles) < 2:
        return None
    
    try:
        prices = [float(c["close"]) for c in candles]
        avg = sum(prices) / len(prices)
        variance = sum((p - avg) ** 2 for p in prices) / len(prices)
        volatility = (variance ** 0.5) / avg * 100
        return volatility
    except:
        return None

def get_trend_emoji(change_pct):
    """Return trend emoji based on price change"""
    if change_pct > 1:
        return "🚀"
    elif change_pct > 0:
        return "📈"
    elif change_pct < -1:
        return "📉"
    elif change_pct < 0:
        return "🔻"
    else:
        return "➡️"

async def fx_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/fx")
    await handle_streak(update, context)
    
    if len(context.args) != 1:
        return await update.message.reply_text(
            "❌ Usage: /fx [pair]\n"
            "Example: /fx eurusd or /fx usd\n\n"
            "📌 Popular pairs: EUR/USD, GBP/USD, USD/JPY"
        )

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

        # Extract data
        price = float(data["close"])
        high_24h = float(data.get("high", 0))
        low_24h = float(data.get("low", 0))
        open_price = float(data.get("open", price))
        prev_close = float(data.get("previous_close", price))
        change_pct = float(data.get("percent_change", 0))
        volume = data.get("volume", "N/A")
        
        # Calculate additional metrics
        daily_range = high_24h - low_24h
        range_pct = (daily_range / low_24h * 100) if low_24h > 0 else 0
        from_open_pct = ((price - open_price) / open_price * 100) if open_price > 0 else 0
        
        # Get trend emoji
        trend = get_trend_emoji(change_pct)

        # Fetch historical data for weekly stats and volatility
        week_high = week_low = volatility = month_change = None
        
        try:
            hist_url = "https://api.twelvedata.com/time_series"
            hist_params = {
                "symbol": pair,
                "interval": "1day",
                "outputsize": 30,  # Get 30 days for better analysis
                "apikey": TWELVE_KEY
            }

            hist_res = requests.get(hist_url, params=hist_params, timeout=10)
            hist_data = hist_res.json()
            candles = hist_data.get("values", [])

            if candles:
                # Weekly high/low (last 7 days)
                week_candles = candles[:7]
                week_high = max(float(c["high"]) for c in week_candles)
                week_low = min(float(c["low"]) for c in week_candles)
                
                # Monthly change (30 days)
                if len(candles) >= 30:
                    month_old_price = float(candles[29]["close"])
                    month_change = ((price - month_old_price) / month_old_price * 100)
                
                # Volatility calculation
                volatility = calculate_volatility(candles[:7])

        except Exception as e:
            print("Historical data fetch failed:", e)

        # Build response message
        text = f"{trend} *Forex Pair: {pair}*\n\n"
        text += f"💵 *Current Rate:* `{price:,.5f}`\n"
        text += f"📊 *24h Change:* {change_pct:+.2f}% ({trend})\n"
        text += f"🕐 *From Open:* {from_open_pct:+.2f}%\n\n"
        
        text += f"📈 *24h High:* `{high_24h:,.5f}`\n"
        text += f"📉 *24h Low:* `{low_24h:,.5f}`\n"
        text += f"📏 *24h Range:* `{daily_range:.5f}` ({range_pct:.2f}%)\n\n"

        if week_high and week_low:
            text += f"📅 *Weekly High:* `{week_high:,.5f}`\n"
            text += f"📅 *Weekly Low:* `{week_low:,.5f}`\n"
        
        if month_change is not None:
            month_emoji = "🟢" if month_change > 0 else "🔴"
            text += f"📆 *30d Change:* {month_emoji} {month_change:+.2f}%\n"
        
        if volatility is not None:
            vol_status = "High" if volatility > 1 else "Moderate" if volatility > 0.5 else "Low"
            text += f"📊 *Volatility (7d):* {vol_status} ({volatility:.2f}%)\n"
        
        text += f"\n🔄 *Previous Close:* `{prev_close:,.5f}`"
        text += f"\n🔓 *Open:* `{open_price:,.5f}`"
        
        if volume != "N/A":
            try:
                vol_formatted = f"{int(volume):,}"
                text += f"\n📊 *Volume:* {vol_formatted}"
            except:
                pass
        

        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        print("FX command error:", e)
        await update.message.reply_text("⚠️ Failed to fetch forex data. Try again later.")