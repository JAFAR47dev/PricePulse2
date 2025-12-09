# handlers/screener.py
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from services.screener_engine import run_screener
from models.user import get_user_plan
from utils.auth import is_pro_plan
from models.user_activity import update_last_active
import asyncio

# Predefined strategies
STRATEGIES = {
    "strat_1": "RSI < 30 + MACD Bullish Condition",
    "strat_2": "EMA Breakout + Volume Surge",
    "strat_3": "RSI Oversold + Bullish Engulfing",
    "strat_4": "MACD Bullish + Golden Cross",
    "strat_5": "Price 5% below 7d average + Trendline Break"
}


async def screener_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/screener")

    plan = get_user_plan(user_id)

    # -------------------------------
    # ❌ Free Plan — Block Access
    # -------------------------------
    if not is_pro_plan(plan):
        upgrade_button = InlineKeyboardMarkup([[
            InlineKeyboardButton("🚀 Upgrade to Pro", callback_data="upgrade_menu")
        ]])
        return await update.message.reply_text(
            "🔒 The *Multi-Coin Screener* is only available to *Pro users*.\n\n"
            "Upgrade now to scan 200+ coins in real-time.",
            reply_markup=upgrade_button,
            parse_mode="Markdown"
        )

    # -------------------------------
    # ✅ Show strategy list
    # -------------------------------
    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"screener_{key}")]
        for key, name in STRATEGIES.items()
    ]

    await update.message.reply_text(
        "📊 *Multi-Coin Screener*\n\nSelect a strategy to scan 200 coins:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def screener_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    plan = get_user_plan(user_id)

    # -------------------------------
    # ❌ Free Plan — Block Access
    # -------------------------------
    if not is_pro_plan(plan):
        return await query.edit_message_text(
            "🔒 This screener is *Pro only*.\nUpgrade to unlock all advanced features.",
            parse_mode="Markdown"
        )

    # Extract chosen strategy
    strategy_key = query.data.replace("screener_", "")
    strategy_name = STRATEGIES.get(strategy_key)

    if not strategy_name:
        return await query.edit_message_text("⚠️ Invalid strategy.")

    # Inform user
    await query.edit_message_text(
        f"🔍 Scanning 200 coins for:\n*{strategy_name}*\n\n"
        "Please wait, usually 10–25 seconds...",
        parse_mode="Markdown"
    )

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # -------------------------------
    # ⏳ 20-second timeout protection
    # -------------------------------
    try:
        results = await asyncio.wait_for(run_screener(strategy_key), timeout=20)

    except asyncio.TimeoutError:
        return await query.message.reply_text(
            "⏳ Screener timed out.\n"
            "The market data provider may be slow — please try again.",
            parse_mode="Markdown"
        )

    # -------------------------------
    # ❌ No matches
    # -------------------------------
    if not results:
        return await query.message.reply_text(
            "❌ No coins matched this strategy right now.\n"
            "Try again later — conditions change fast.",
            parse_mode="Markdown"
        )

    # -------------------------------
    # ✅ Output top matches
    # -------------------------------
    msg = f"✅ *Top Matches ({len(results)} found):*\n\n"

    for i, coin in enumerate(results[:10], 1):
        msg += (
            f"{i}. *{coin['symbol']}* — Score: `{coin['score']}`\n"
            f"   Price: `${coin['close']:.2f}` | RSI: `{coin['rsi']:.1f}`\n\n"
        )

    await query.message.reply_text(msg, parse_mode="Markdown")