import os
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes

# === File path ===
USER_TRACK_FILE = "whales/user_tracking.json"


# === Helpers ===
def load_user_tracking():
    if not os.path.exists(USER_TRACK_FILE):
        return {}
    with open(USER_TRACK_FILE, "r") as f:
        return json.load(f)


def save_user_tracking(data):
    with open(USER_TRACK_FILE, "w") as f:
        json.dump(data, f, indent=2)


# === /untrack Command ===
async def untrack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /untrack [token] or /untrack all
    """
    user_id = str(update.effective_user.id)
    tracking_data = load_user_tracking()
    user_data = tracking_data.get(user_id, {}).get("tracked", [])

    if len(context.args) == 1 and context.args[0].lower() == "all":
        # Clear all tracked tokens
        if not user_data:
            await update.message.reply_text("⚠️ You’re not tracking any whales.")
            return

        tracking_data[user_id] = {"tracked": []}
        save_user_tracking(tracking_data)

        await update.message.reply_text("🗑️ All whale tracking cleared.")
        return

    if not user_data:
        await update.message.reply_text("🐋 You’re not tracking any whales yet.")
        return

    # Show inline buttons for tracked tokens
    buttons = [
        [InlineKeyboardButton(f"❌ Untrack {t['token']}", callback_data=f"untrack:{t['token']}")]
        for t in user_data
    ]

    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(
        "Select a token to untrack:",
        reply_markup=reply_markup,
    )


# === Callback Handler ===
async def untrack_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, token = query.data.split(":")
    user_id = str(query.from_user.id)

    tracking_data = load_user_tracking()
    user_data = tracking_data.get(user_id, {}).get("tracked", [])

    new_list = [t for t in user_data if t["token"] != token]

    if len(new_list) == len(user_data):
        await query.edit_message_text(f"⚠️ You weren’t tracking *{token}*.", parse_mode="Markdown")
        return

    tracking_data[user_id] = {"tracked": new_list}
    save_user_tracking(tracking_data)

    await query.edit_message_text(f"❌ You’ve stopped tracking *{token}* whales.", parse_mode="Markdown")


# === Register handler ===
def register_untrack_handler(app):
    app.add_handler(CommandHandler("untrack", untrack_command))
    app.add_handler(CallbackQueryHandler(untrack_callback, pattern=r"^untrack:"))