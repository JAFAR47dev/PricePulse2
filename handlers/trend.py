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
            "🔒 Only the *1h* timeframe is available on Free Plan.\nUse /upgrade to unlock more.",
            parse_mode="Markdown"
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")


    try:
        indicators = await get_crypto_indicators(symbol, timeframe)
        if not indicators:
            await update.message.reply_text("⚠️ Could not fetch indicator data.")
            return

        def safe_float(v):
            try:
                return float(v)
            except:
                return None

        # Extract all indicators
        price = safe_float(indicators.get("price"))
        rsi = safe_float(indicators.get("rsi"))
        ema20 = safe_float(indicators.get("ema20"))
        macd = safe_float(indicators.get("macd"))
        macd_signal = safe_float(indicators.get("macdSignal"))
        macd_hist = safe_float(indicators.get("macdHist"))

        # NEW INDICATORS
        stochK = safe_float(indicators.get("stochK"))
        stochD = safe_float(indicators.get("stochD"))
        cci = safe_float(indicators.get("cci"))
        atr = safe_float(indicators.get("atr"))
        mfi = safe_float(indicators.get("mfi"))
        bbUpper = safe_float(indicators.get("bbUpper"))
        bbMiddle = safe_float(indicators.get("bbMiddle"))
        bbLower = safe_float(indicators.get("bbLower"))
        adx = safe_float(indicators.get("adx"))
        vwap = safe_float(indicators.get("vwap"))

        
        # ---------------------- BUILD MESSAGE ----------------------
        msg = f"📊 *Trend Analysis for {symbol}* ({timeframe})\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━\n"

        # PRICE
        msg += f"💰 *Price:* `${price:.2f}`\n" if price else "💰 *Price:* `N/A`\n"

        msg += "\n📈 *Indicators:*\n"

        # RSI
        if rsi:
            if rsi > 70: r = "🔺 Overbought"
            elif rsi < 30: r = "🔻 Oversold"
            else: r = "🟡 Neutral"
            msg += f"• *RSI:* `{rsi:.2f}` → {r}\n"
        else:
            msg += "• RSI: `N/A`\n"

        # MACD
        if macd is not None:
            trend = "🔼 Bullish" if macd > macd_signal else "🔽 Bearish"
            msg += f"• *MACD:* `{macd}` | Signal `{macd_signal}`\n"
            msg += f"  Histogram: `{macd_hist}` → {trend}\n"
        else:
            msg += "• MACD: `N/A`\n"

        # EMA20
        msg += f"• *EMA20:* `${ema20:.2f}`\n" if ema20 else "• EMA20: `N/A`\n"

        # STOCHASTIC
        if stochK and stochD:
            msg += f"• *Stoch K:* `{stochK}` | *D:* `{stochD}`\n"
        else:
            msg += "• Stochastic: `N/A`\n"

        # CCI
        msg += f"• *CCI:* `{cci}`\n" if cci else "• CCI: `N/A`\n"

        # ATR
        msg += f"• *ATR:* `{atr}`\n" if atr else "• ATR: `N/A`\n"

        # MFI
        if mfi:
            if mfi > 80: m = "🔺 Overbought"
            elif mfi < 20: m = "🔻 Oversold"
            else: m = "🟡 Neutral"
            msg += f"• *MFI:* `{mfi}` → {m}\n"
        else:
            msg += "• MFI: `N/A`\n"

        # ADX
        if adx is not None:
            if adx >= 25: a = "💪 Strong Trend"
            else: a = "⚖️ Weak/No Trend"
            msg += f"• *ADX:* `{adx:.2f}` → {a}\n"
        else:
            msg += "• ADX: `N/A`\n"

        # VWAP
        msg += f"• *VWAP:* `${vwap:.2f}`\n" if vwap else "• VWAP: `N/A`\n"

        # BOLLINGER BANDS
        if bbUpper and bbMiddle and bbLower:
            msg += "\n📉 *Bollinger Bands:*\n"
            msg += f"• Upper: `${bbUpper}`\n"
            msg += f"• Middle: `${bbMiddle}`\n"
            msg += f"• Lower: `${bbLower}`\n"
        else:
            msg += "\n📉 Bollinger Bands: `N/A`\n"
    
            await update.message.reply_text(msg, parse_mode="Markdown")

    except Exception as e:
        print("Trend command error:", e)
        await update.message.reply_text("❌ Error fetching trend data.")
                