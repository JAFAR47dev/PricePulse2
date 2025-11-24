import os
import json
from datetime import datetime
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes
from models.user_activity import update_last_active

# === File paths ===
WHALE_DATA_DIR = "whales/data"
USER_TRACK_FILE = "whales/user_tracking.json"
os.makedirs(WHALE_DATA_DIR, exist_ok=True)

# Ensure tracking file exists
if not os.path.exists(USER_TRACK_FILE):
    with open(USER_TRACK_FILE, "w") as f:
        json.dump({}, f, indent=2)


# === Helper functions ===
def load_json_file(path):
    """Safely load a JSON file."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None


def load_user_tracking():
    with open(USER_TRACK_FILE, "r") as f:
        return json.load(f)


def save_user_tracking(data):
    with open(USER_TRACK_FILE, "w") as f:
        json.dump(data, f, indent=2)


# === /track Command Handler ===
async def track_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Usage: /track [token] [no_of_whales]
    Example: /track ETH 20
    """
    user_id = str(update.effective_user.id)
    await update_last_active(user_id, command_name="/track")

    # --- Parse command arguments ---
    if len(context.args) == 0:
        await update.message.reply_text(
            "⚠️ Usage: `/track [token] [no_of_whales]`\nExample: `/track ETH 20`",
            parse_mode="Markdown",
        )
        return

    token = context.args[0].upper()
    limit = 100  # default
    if len(context.args) >= 2:
        try:
            limit = int(context.args[1])
            if limit <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "⚠️ Invalid number format. Example: `/track ETH 10`",
                parse_mode="Markdown",
            )
            return

    # --- Validate whale data file ---
    whale_file = os.path.join(WHALE_DATA_DIR, f"{token}.json")
    if not os.path.exists(whale_file):
        await update.message.reply_text(
            f"❌ Whale data for *{token}* not found.\nPlease ensure it’s among the top 100 ERC20 tokens.",
            parse_mode="Markdown",
        )
        return

    whale_data = load_json_file(whale_file)
    if not whale_data:
        await update.message.reply_text(
            f"⚠️ Could not read whale data for *{token}*. Please try again later.",
            parse_mode="Markdown",
        )
        return

    # --- Check if it's a valid ERC20 token ---
    if whale_data.get("unsupported"):
        reason = whale_data.get("reason", "Unsupported token type.")
        await update.message.reply_text(
            f"⚠️ *{token}* cannot be tracked.\nReason: {reason}",
            parse_mode="Markdown",
        )
        return

    # --- Load or create user tracking data ---
    tracking_data = load_user_tracking()
    user_data = tracking_data.get(user_id, {"tracked": []})

    # Prevent duplicate tracking
    if any(t["token"] == token for t in user_data["tracked"]):
        await update.message.reply_text(
            f"⚠️ You’re already tracking *{token}* whales.",
            parse_mode="Markdown",
        )
        return

    # --- Add tracking record ---
    user_data["tracked"].append({
        "token": token,
        "limit": limit,
        "added_at": datetime.utcnow().isoformat() + "Z"
    })
    tracking_data[user_id] = user_data
    save_user_tracking(tracking_data)

    # ✅ Success message
    await update.message.reply_text(
        f"✅ You’re now tracking the top {limit} *{token}* whales.",
        parse_mode="Markdown",
    )


# === Function to register handler ===
def register_track_handler(app):
    app.add_handler(CommandHandler("track", track_command))