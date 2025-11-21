# handlers/aiscan.py
import os
import requests
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from utils.ohlcv import fetch_candles
from utils.patterns import (
    detect_divergences,
    detect_engulfing_patterns,
    detect_trendline_breaks,
    detect_golden_death_crosses,
    detect_double_top_bottom
)
import datetime
from models.user import get_user_plan
from utils.auth import is_pro_plan
from models.user_activity import update_last_active

VALID_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "8h", "1d"]


async def aiscan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    plan = get_user_plan(user_id)
    await update_last_active(user_id)

    if not is_pro_plan(plan):
        await update.message.reply_text(
            "🔒 This is a *Pro-only* feature.\nUpgrade to unlock AI backtesting.\n\n👉 /upgrade",
            parse_mode=ParseMode.MARKDOWN
        )
        return
        
    args = context.args
    if len(args) < 1:
        return await update.message.reply_text(
            "❌ Usage: /aiscan BTC [timeframe]\nExample: /aiscan ETH 1h"
        )

    symbol = args[0].upper()
    tf = args[1] if len(args) > 1 else "1h"

    if tf not in VALID_TIMEFRAMES:
        return await update.message.reply_text(
            "❌ Invalid timeframe. Choose from: 1m, 5m, 15m, 30m, 1h, 2h, 4h, 8h, 1d"
        )

    await update.message.reply_text(f"🔍 Scanning {symbol} ({tf}) for patterns...")

    candles = await fetch_candles(symbol, tf)
    if not candles:
        return await update.message.reply_text("⚠️ Failed to fetch chart data.")

    # Detect all patterns
    patterns = (
        detect_divergences(candles)
        + detect_engulfing_patterns(candles)
        + detect_trendline_breaks(candles)
        + detect_golden_death_crosses(candles)
        + detect_double_top_bottom(candles)
    )

    # Log only recent and major patterns (most recent 5)
    if patterns:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print("\n🧠 [AI Pattern Spotter Log]")
        print(f"Time: {timestamp}")
        print(f"Symbol: {symbol} | Timeframe: {tf}")
        print(f"Detected {len(patterns)} patterns (showing latest 5):")

        for i, p in enumerate(patterns[-5:], 1):
            print(f"  {i}. {p}")

        print("-" * 50)

        formatted_patterns = "\n".join([f"• {p}" for p in patterns[:5]])
        await update.message.reply_text(
            f"📊 *Major Patterns Found for {symbol} ({tf})*\n\n{formatted_patterns}",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        print(f"🧠 [{symbol}] No major patterns detected.")
        await update.message.reply_text("✅ No major chart patterns detected.")
        
    # AI market summary
    summary = await get_ai_pattern_summary(symbol, tf, patterns[-20:])

    if summary:
        await update.message.reply_text(
            f"🤖 *Chart Summary for {symbol} ({tf}):*\n\n{summary}",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text("⚠️ AI summary failed. Please try again later.")

# AI helper
async def get_ai_pattern_summary(symbol, timeframe, patterns):
    pattern_text = "\n".join(f"- {p}" for p in patterns)

    prompt = f"""
You are a professional crypto market analyst.

A pattern scan for {symbol} on the {timeframe} timeframe detected:

{pattern_text}

Based on these signals:
1. What direction is the market likely to move?
2. Are bulls or bears gaining strength?
3. Which patterns are most relevant?
4. What advice would you give to traders?

Return a concise summary in under 150 words. Avoid technical terms. Make it actionable and easy to understand for everyday traders.
"""

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "model": "mistralai/mixtral-8x7b-instruct",
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=20
        )

        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"].strip()
        else:
            print("AI response error:", response.status_code, response.text)
            return None

    except Exception as e:
        print("AI summary exception:", e)
        return None