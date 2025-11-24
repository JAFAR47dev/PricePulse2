from telegram import Update
from telegram.ext import ContextTypes
from models.user import get_user_plan
from utils.tradingview import generate_chart_image 
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

VALID_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]

async def show_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/chart")
    await handle_streak(update, context)
    args = context.args

    # Handle both /chart command and inline button (fallback to callback data)
    message = update.message or update.callback_query.message

    if not args:
        await message.reply_text(
            "❌ Usage: `/c BTC [timeframe]`\nExample: `/c BTC 1h`",
            parse_mode="Markdown"
        )
        return

    symbol_input = args[0].upper()
    symbol = symbol_input if symbol_input.endswith("USDT") else symbol_input + "USDT"
    timeframe = args[1].lower() if len(args) > 1 else "1h"

    if timeframe not in VALID_TIMEFRAMES:
        await message.reply_text(
            "❌ Invalid timeframe. Valid options: `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`",
            parse_mode="Markdown"
        )
        return

    plan = get_user_plan(user_id)
    if plan == "free" and timeframe != "1h":
        await message.reply_text(
            "🔒 Only the `1h` chart is available for Free users.\nUse /upgrade to unlock other timeframes: 1m, 5m, 15m, 30m, 4h, 1d.",
            parse_mode="Markdown"
        )
        return

    loading_msg = await message.reply_text("⏳ Generating chart... please wait.")
    image_bytes = await generate_chart_image(symbol, timeframe, context)

    if not image_bytes:
        await loading_msg.edit_text("⚠️ Failed to load chart. Try again later.")
        return

    await loading_msg.delete()
    await message.reply_photo(
        photo=image_bytes,
        caption=f"📈 *{symbol}* — {timeframe.upper()} Chart (TradingView)",
        parse_mode="Markdown"
    )