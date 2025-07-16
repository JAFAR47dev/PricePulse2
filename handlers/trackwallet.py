
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from utils.auth import is_pro_plan
from models.user import get_user_plan
from models.wallet_tracker import save_tracked_wallet

AWAITING_WALLET = 1

TOP_WHALES = {
    "Binance Cold Wallet": "0x1234...abcd",
    "Justin Sun": "0x4567...efgh",
    "Crypto.com": "0x8910...ijkl",
}

# /trackwallet command
async def trackwallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    plan = get_user_plan(user_id)

    if not is_pro_plan(plan):
        return await update.message.reply_text(
            "🔒 This feature is available for *Pro users only*.\nUpgrade to track whale wallet activity.",
            parse_mode=ParseMode.MARKDOWN
        )

    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"trackwhale_{addr}")]
        for name, addr in TOP_WHALES.items()
    ]
    keyboard.append([InlineKeyboardButton("🔍 Track Custom Wallet", callback_data="trackwhale_custom")])

    await update.message.reply_text(
        "🐋 *Whale Wallet Tracker*\n\nSelect a top wallet or enter a custom address:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

# Handles whale button press or custom option
async def trackwallet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    if data == "trackwhale_custom":
        await query.message.reply_text("🔢 Please send the wallet address you want to track:")
        return AWAITING_WALLET

    # Normal whale option
    wallet = data.replace("trackwhale_", "")
    save_tracked_wallet(user_id, wallet)
    await query.edit_message_text(f"✅ You’re now tracking: `{wallet}`", parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END

# Handles manual wallet address input
async def receive_wallet_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    address = update.message.text.strip()
    user_id = update.effective_user.id

    if not address.startswith("0x") or len(address) < 30:
        return await update.message.reply_text("❌ Invalid address. Please enter a valid Ethereum address.")

    save_tracked_wallet(user_id, address)
    await update.message.reply_text(f"✅ You’re now tracking: `{address}`", parse_mode=ParseMode.MARKDOWN)
    return ConversationHandler.END

# Export handlers to main.py
trackwallet_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("track", trackwallet_command)],
    states={
        AWAITING_WALLET: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_wallet_input)],
    },
    fallbacks=[],
    allow_reentry=True,
)

trackwallet_callback_handler = CallbackQueryHandler(trackwallet_callback, pattern=r"^trackwhale_")