from utils.indicators import get_crypto_indicators
from models.user import get_user_plan
from utils.auth import is_pro_plan
from telegram import Update
from telegram.ext import ContextTypes
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

async def trend_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/trend")
    await handle_streak(update, context)
    args = context.args

    if not args:
        await update.message.reply_text("❌ Usage: /trend BTC [timeframe]\nExample: /trend ETH 4h")
        return

    symbol = args[0].upper().replace("USDT", "") + "/USDT"
    timeframe = args[1] if len(args) > 1 else "1h"
    allowed_timeframes = ["1h", "4h", "1d", "30m", "15m"]

    if timeframe not in allowed_timeframes:
        await update.message.reply_text("❌ Invalid timeframe. Use one of: 1h, 4h, 1d, 30m, 15m")
        return

    plan = get_user_plan(user_id)
    if plan == "free" and timeframe != "1h":
        await update.message.reply_text(
            "🔒 Only the *1h* timeframe is available on Free Plan.\nUse /upgrade@EliteTradeSignalBot to unlock more.",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text("📡 Analyzing trend data... please wait.")

    try:
        indicators = await get_crypto_indicators(symbol, timeframe)
        if not indicators:
            await update.message.reply_text("⚠️ Could not fetch indicator data.")
            return

        # Safely extract values (convert to float if possible)
        def safe_float(value):
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        price = safe_float(indicators.get("price"))
        rsi = safe_float(indicators.get("rsi"))
        ema20 = safe_float(indicators.get("ema20"))
        macd = safe_float(indicators.get("macd"))
        macd_signal = safe_float(indicators.get("macdSignal"))
        macd_hist = safe_float(indicators.get("macdHist"))

        msg = f"📊 *Trend Analysis for {symbol}* ({timeframe})\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━\n"

        # Price
        if price is not None:
            msg += f"💰 *Price:* `${price:.2f}`\n"
        else:
            msg += "💰 *Price:* `N/A`\n"

        # RSI
        if rsi is not None:
            if rsi > 70:
                rsi_trend = "🔺 *Overbought*"
            elif rsi < 30:
                rsi_trend = "🔻 *Oversold*"
            else:
                rsi_trend = "🟡 *Neutral*"
            msg += f"📉 *RSI:* `{rsi:.2f}` → {rsi_trend}\n"
        else:
            msg += "📉 *RSI:* `N/A`\n"

        # MACD
        if macd is not None and macd_signal is not None:
            macd_trend = "🔼 Bullish" if macd > macd_signal else "🔽 Bearish"
            msg += f"📈 *MACD:* `{macd}`\n"
            msg += f"📊 *Signal:* `{macd_signal}`\n"
            msg += f"🧮 *Histogram:* `{macd_hist if macd_hist is not None else 'N/A'}` → {macd_trend}\n"
        else:
            msg += "📈 *MACD:* `N/A`\n"

        # EMA
        if ema20 is not None:
            msg += f"📏 *EMA(20):* `${ema20:.2f}`\n"
        else:
            msg += "📏 *EMA(20):* `N/A`\n"

        await update.message.reply_text(msg, parse_mode="Markdown")

    except Exception as e:
        print("Trend command error:", e)
        await update.message.reply_text("❌ Error fetching trend data.")