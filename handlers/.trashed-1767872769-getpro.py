from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

BOT_USERNAME = "EliteTradeSignalBot"  # Your bot username
REF_DEEPLINK_PREFIX = f"https://t.me/{BOT_USERNAME}?start=ref"

async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    referral_link = f"{REF_DEEPLINK_PREFIX}{user_id}"

    keyboard = [
        [InlineKeyboardButton("➡️ Check My Progress", callback_data="check_referral_progress")],
        [InlineKeyboardButton("➡️ Submit Proof (Task 2)", url=f"https://t.me/{BOT_USERNAME}?start=submitproof_task2")],
        [InlineKeyboardButton("➡️ Submit Proof (Task 3)", url=f"https://t.me/{BOT_USERNAME}?start=submitproof_task3")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = (
        "📋 *Tasks – Complete These to Unlock a Surprise Gift 🎁*\n\n"
        "Help us grow and earn something special. Complete all 3 tasks below:\n\n"
        "–––\n\n"
        "1️⃣ *Invite 3 New Users*\n"
        "Bring in 3 friends who start the bot and set up at least 1 alert.\n\n"
        f"🔗 *Your referral link:*\nhttps://t.me/{BOT_USERNAME}?start=ref{user_id}\n\n"
        "–––\n\n"
        "2️⃣ *Post in a Large Crypto Group or Channel (5k+ members)*\n"
        "Tell others about this bot and why you like it.\n\n"
        "–––\n\n"
        "3️⃣ *Post on Twitter or Reddit*\n"
        "Make a post with a screenshot or short review about the bot on X or Reddit.\nMust mention at least 1 feature.\n\n"
        "–––\n\n"
        "✅ When you're done, the surprise reward will be unlocked for you 🎁\n"
        "Keep going — you're almost there! 🚀"
    )

    await update.message.reply_text(message, reply_markup=reply_markup, parse_mode="Markdown")