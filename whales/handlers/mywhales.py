import os
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes

# === File paths ===
USER_TRACK_FILE = "whales/user_tracking.json"
WHALE_DATA_DIR = "whales/data"


# === Helper: Load tracking data ===
def load_user_tracking():
    if not os.path.exists(USER_TRACK_FILE):
        return {}
    with open(USER_TRACK_FILE, "r") as f:
        return json.load(f)


def load_whale_data(symbol: str):
    """Load whale data for a token (from whales/data)"""
    file_path = os.path.join(WHALE_DATA_DIR, f"{symbol}.json")
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except Exception:
        return None


# === /mywhales Command ===
async def mywhales_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    tracking_data = load_user_tracking()
    user_data = tracking_data.get(user_id, {}).get("tracked", [])

    if not user_data:
        await update.message.reply_text(
            "🐋 You’re not tracking any whales yet.\nUse /track to begin."
        )
        return

    text_lines = ["🐋 *Your Whale Tracking:*"]
    buttons = []

    for idx, t in enumerate(user_data, start=1):
        token = t["token"]
        limit = t["limit"]
        text_lines.append(f"{idx}️⃣ {token} — Top {limit}")

        # Each token gets its own inline button
        buttons.append(
            [InlineKeyboardButton(f"📊 View {token} Whales", callback_data=f"view_whales:{token}")]
        )

    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(
        "\n".join(text_lines),
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


# === Callback for "View Whale List" button ===
async def view_whales_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, token = query.data.split(":")
    whale_data = load_whale_data(token)

    if not whale_data or "whales" not in whale_data:
        await query.edit_message_text(f"⚠️ Whale data for *{token}* not available.", parse_mode="Markdown")
        return

    whales = whale_data["whales"]
    preview_count = min(10, len(whales))  # Show only top 10 for preview
    lines = [f"🐋 *Top {preview_count} {token} Whales:*"]

    for w in whales[:preview_count]:
        lines.append(f"{w['rank']}. `{w['address']}` — {w['share']}%")

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="Markdown",
    )


# === Register handlers ===
def register_mywhales_handler(app):
    app.add_handler(CommandHandler("mywhales", mywhales_command))
    app.add_handler(CallbackQueryHandler(view_whales_callback, pattern=r"^view_whales:"))