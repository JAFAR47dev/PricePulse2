from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

async def add_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_username = context.bot.username

    keyboard = [
        [InlineKeyboardButton("➕ Add me to a Group", url=f"https://t.me/{bot_username}?startgroup=true")]
    ]

    await update.message.reply_text(
        "👥 *Add me to your Telegram Group*\n\n"
        "Tap the button below to add me to any of your groups.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )