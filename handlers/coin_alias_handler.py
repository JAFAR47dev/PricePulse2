from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters
)
from services.coin_data import get_coin_data
from utils.formatting import format_large_number
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

async def handle_chart_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        parts = query.data.split("_")
        if len(parts) == 3 and parts[0] == "chart":
            symbol = parts[1]
            timeframe = parts[2]

            from .chart import show_chart
            context.args = [symbol, timeframe]
            await show_chart(update, context)
        else:
            await query.message.reply_text("⚠️ Invalid chart data.")
    except Exception as e:
        await query.message.reply_text(f"❌ Error: {e}")

async def handle_add_alert_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    if len(parts) == 2 and parts[0] == "addalert":
        symbol = parts[1]
        await query.message.reply_text(
            f"🛎 To add an alert for *{symbol}*, use:\n\n"
            f"`/set`\n",
            parse_mode="Markdown"
        )

async def coin_alias_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/coin_alias")
    await handle_streak(update, context)
    cmd = update.message.text.strip().lstrip("/")
    coin_data = get_coin_data(cmd)

    if not coin_data:
        await update.message.reply_text(f"❌ Coin `{cmd}` not found.", parse_mode="Markdown")
        return

    m = coin_data["market_data"]
    pc_1h = m["price_change_percentage_1h_in_currency"].get("usd", 0)
    pc_24h = m["price_change_percentage_24h_in_currency"].get("usd", 0)
    pc_7d = m["price_change_percentage_7d_in_currency"].get("usd", 0)
    pc_30d = m["price_change_percentage_30d_in_currency"].get("usd", 0)
    price = m["current_price"]["usd"]
    ath = m["ath"]["usd"]
    vol = m["total_volume"]["usd"]
    cap = m["market_cap"]["usd"]
    high = m["high_24h"]["usd"]
    low = m["low_24h"]["usd"]

    # ✅ Calculate % difference from ATH to current price
    if ath > 0:
        ath_change_pct = ((price - ath) / ath) * 100
    else:
        ath_change_pct = 0

    ath_display = format_large_number(ath)
    vol_display = format_large_number(vol)
    cap_display = format_large_number(cap)

    # ✅ Build message with ATH % difference
    msg = f"""📊 *{coin_data['name']}* (`{coin_data['symbol'].upper()}`)

💰 Price: `${price:,.3f}`
📈 24h High: `${high:,.3f}`
📉 24h Low: `${low:,.3f}`
🕐 1h: {pc_1h:.2f}%
📅 24h: {pc_24h:.2f}%
📆 7d: {pc_7d:.2f}%
🗓 30d: {pc_30d:.2f}%
📛 ATH: `${ath_display}` ({ath_change_pct:+.2f}%)
🔁 24h Volume: `${vol_display}`
🌍 Market Cap: `${cap_display}`
"""

    symbol_upper = coin_data["symbol"].upper()
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📈 View Chart", callback_data=f"chart_{symbol_upper}_1h"),
            InlineKeyboardButton("➕ Add Alert", callback_data=f"addalert_{symbol_upper}")
        ]
    ])

    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)
    
EXCLUDED_COMMANDS = {
    "start", "help", "tasks", "referral", "referrals", "alerts", "watch", "watchlist",
    "upgrade", "remove", "removeall", "best", "worst", "news", "trend", "addasset",
    "portfolio", "portfoliotarget", "portfoliolimit", "prediction", "edit", "stats",
    "setplan", "prolist", "calc", "aistrat", "screen", "aiscan", "hmap", "track", "cal", "fxcal", "fxsessions"
}

async def coin_command_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    command = update.message.text.strip().lstrip("/").lower()

    if command in EXCLUDED_COMMANDS:
        return  # Skip — handled by specific command handlers

    await coin_alias_handler(update, context)