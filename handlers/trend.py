from utils.indicators import get_crypto_indicators
from models.user import get_user_plan
from utils.auth import is_pro_plan
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters
)

async def trend_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    if not args:
        await update.message.reply_text("❌ Usage: /trend BTC [timeframe]\nExample: /trend ETH 4h")
        return

    symbol = args[0].upper()
    symbol = symbol.upper().replace("USDT", "") + "/USDT"
    timeframe = args[1] if len(args) > 1 else "1h"
    
   

    allowed_timeframes = ["1h", "4h", "1d", "30m", "15m"]
    if timeframe not in allowed_timeframes:
        await update.message.reply_text("❌ Invalid timeframe. Use one of: 1h, 4h, 1d, 30m, 15m")
        return

    # Check user plan
    plan = get_user_plan(user_id)
    if plan == "free" and timeframe != "1h":
        await update.message.reply_text("🔒 Only the *1h* timeframe is available on Free Plan.\nUse /upgrade@EliteTradeSignalBot to unlock more.", parse_mode="Markdown")
        return

    await update.message.reply_text("📡 Analyzing trend data... please wait.")

    try:
        indicators = await get_crypto_indicators(symbol, timeframe)
        if not indicators:
            await update.message.reply_text("⚠️ Could not fetch indicator data.")
            return

        msg = f"📊 *Trend Analysis for {symbol}* ({timeframe})\n"
        msg += f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"💰 *Price:* `${indicators['price']:.2f}`\n"
        
        # RSI interpretation
        rsi = indicators["rsi"]
        if rsi > 70:
            rsi_trend = "🔺 *Overbought*"
        elif rsi < 30:
            rsi_trend = "🔻 *Oversold*"
        else:
            rsi_trend = "🟡 *Neutral*"
        msg += f"📉 *RSI:* `{rsi:.2f}` → {rsi_trend}\n"

        # MACD with direction indication
        macd = indicators["macd"]
        signal = indicators["macdSignal"]
        hist = indicators["macdHist"]
        macd_trend = "🔼 Bullish" if float(macd) > float(signal) else "🔽 Bearish"
        msg += f"📈 *MACD:* `{macd}`\n"
        msg += f"📊 *Signal:* `{signal}`\n"
        msg += f"🧮 *Histogram:* `{hist}` → {macd_trend}\n"

        # EMA
        msg += f"📏 *EMA(20):* `${indicators['ema20']:.2f}`\n"
        

        await update.message.reply_text(msg, parse_mode="Markdown")

    except Exception as e:
        print("Trend command error:", e)
        await update.message.reply_text("❌ Error fetching trend data.")
        
