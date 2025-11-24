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
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_streak(update, context)
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/referral")
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
        f"🎯 Use /tasks to complete tasks and unlock Pro access!\n",
        parse_mode="Markdown"
    )