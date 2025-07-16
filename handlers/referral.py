from models.db import get_connection
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters
)

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={user_id}"

    # Get referral count from referrals table
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
    count = cursor.fetchone()[0]
    conn.close()

    await update.message.reply_text(
        f"📣 *Invite friends & earn rewards!*\n\n"
        f"🔗 *Your referral link:*\n{link}\n\n"
        f"👥 *Referrals so far:* {count}\n\n"
        f"🎯 Use /tasks to complete tasks and unlock Pro access!\n"
        f"💎 You also get credit when your friends join via your link.",
        parse_mode="Markdown"
    )