# handlers/fav/fav_handler.py

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from handlers.fav.utils.db_favorites import add_favorite, remove_favorite, get_favorites

async def fav_command(update, context):
    keyboard = [
        [
            InlineKeyboardButton("💰 Prices", callback_data="fav_prices"),
            InlineKeyboardButton("➕ Add Favorite", callback_data="fav_add")
        ],
        [
            InlineKeyboardButton("📋 List Favorites", callback_data="fav_list"),
            InlineKeyboardButton("➖ Remove Favorite", callback_data="fav_remove")
        ]
    ]

    await update.message.reply_text(
        "⭐ *Favorites Menu* — choose an action:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    
async def fav_text_handler(update, context):
    mode = context.user_data.get("fav_mode")
    if not mode:
        return  # Not in /fav mode

    symbol = update.message.text.strip().upper()
    user_id = update.effective_user.id

    if mode == "add":
        add_favorite(user_id, symbol)
        await update.message.reply_text(f"✅ Added *{symbol}* to favorites!", parse_mode="Markdown")

    elif mode == "remove":
        remove_favorite(user_id, symbol)
        await update.message.reply_text(f"❌ Removed *{symbol}* from favorites.", parse_mode="Markdown")

    # Clear mode
    context.user_data["fav_mode"] = None