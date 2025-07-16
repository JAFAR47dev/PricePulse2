# handlers/screener.py

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CallbackQueryHandler
from services.screener_engine import run_screener
from models.user import get_user_plan
from utils.auth import is_pro_plan
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

# Predefined strategies
STRATEGIES = {
    "strat_1": "RSI < 30 + MACD Crossover",
    "strat_2": "EMA Breakout + Volume Surge",
    "strat_3": "RSI Oversold + Bullish Engulfing",
    "strat_4": "MACD Bullish + Golden Cross",
    "strat_5": "Price 5% below 7d average + Trendline Break"
}


async def screener_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    plan = get_user_plan(user_id)  # ✅ Removed `await`

    if not is_pro_plan(plan):
        upgrade_button = InlineKeyboardMarkup([[
            InlineKeyboardButton("🚀 Upgrade to Pro", callback_data="upgrade_menu")
        ]])
        return await update.message.reply_text(
            "🔒 The *Multi-Coin Screener* is available to *Pro users only*.\n\n"
            "Upgrade now to scan 200+ coins for real-time setups.",
            reply_markup=upgrade_button,
            parse_mode="Markdown"
        )

    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"screener_{key}")]
        for key, name in STRATEGIES.items()
    ]

    await update.message.reply_text(
        "📊 *Multi-Coin Screener*\n\nSelect a strategy to scan 200+ coins:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    
async def screener_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    plan = get_user_plan(user_id)  # Removed await

    if not is_pro_plan(plan):
        await query.answer()
        return await query.edit_message_text(
            "🔒 This screener feature is for *Pro users only*.\n\n"
            "Upgrade to unlock real-time multi-coin scanning.",
            parse_mode="Markdown"
        )

    await query.answer()

    strategy_key = query.data.replace("screener_", "")
    strategy_name = STRATEGIES.get(strategy_key)

    if not strategy_name:
        return await query.edit_message_text("⚠️ Invalid strategy.")

    await query.edit_message_text(
        f"🔍 Scanning top 200 coins for:\n*{strategy_name}*\n\nPlease wait, this may take ~30s...",
        parse_mode="Markdown"
    )
    
    results = await run_screener(strategy_key)

    if not results:
        return await query.message.reply_text("❌ No coins matched this strategy right now.")

    msg = f"✅ *Top Matches ({len(results)} coins found):*\n\n"
    for i, coin in enumerate(results[:10], 1):  # Show top 10 only
        msg += (
            f"{i}. *{coin['symbol']}* — Score: `{coin.get('score', 'N/A')}`\n"
            f"   Price: `${coin['close']:.2f}` | RSI: `{coin['rsi']:.1f}`\n\n"
        )

    await query.message.reply_text(msg, parse_mode="Markdown")