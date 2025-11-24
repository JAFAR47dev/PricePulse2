from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, ContextTypes
from models.user_activity import update_last_active

FEEDBACK_URL = "https://toptelegrambots.com/list/EliteTradeSignalBot"

# === /feedback Command ===
async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/feedback")

    text = (
        "💬 *We’d love your feedback!*\n\n"
        "If you enjoy using *PricePulseBot*, please take a moment to leave a review 💫\n"
        "Your feedback helps us grow and reach more traders 🚀"
    )

    keyboard = [
        [InlineKeyboardButton("⭐ Leave a Review", url=FEEDBACK_URL)],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


# === Register handler ===
def register_feedback_handler(app):
    app.add_handler(CommandHandler("feedback", feedback_command))