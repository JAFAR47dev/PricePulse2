# handlers/set_alert/set_alert.py

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from models.user import get_user_plan
from utils.auth import is_pro_plan
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

# Import the new interactive flow starter
from handlers.set_alert.flow_manager import start_set_alert

# Import existing alert handlers (for backward compatibility)
from handlers.alert_handlers import (
    handle_price_alert,
    handle_percent_alert,
    handle_volume_alert,
    handle_risk_alert,
    handle_custom_alert,
)

async def set_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Entry point for /set command.
    If user provides arguments, fall back to old behavior.
    If no args, launch interactive alert setup flow.
    """
    user_id = update.effective_user.id
    await update_last_active(user_id)
    await handle_streak(update, context)
    plan = get_user_plan(user_id)

    # ✅ If user typed just /set → start interactive flow
    if not context.args:
        await start_set_alert(update, context)
        return

    # --- Existing logic (legacy command format) ---
    args = context.args
    alert_type = args[0].lower()

    handlers = {
        "price": handle_price_alert,
        "percent": handle_percent_alert,
        "volume": handle_volume_alert,
        "risk": handle_risk_alert,
        "custom": handle_custom_alert,
    }

    if alert_type not in handlers:
        await update.message.reply_text(
            "❌ Invalid alert type.\nUse one of: price, percent, volume, risk, custom"
        )
        return

    # 🚫 Enforce free plan limits
    if not is_pro_plan(plan) and alert_type != "price":
        await update.message.reply_text(
            "🚫 Advanced alerts are for *Pro users* only.\nUse /upgrade to unlock.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ✅ Pass arguments to correct handler
    await handlers[alert_type](update, context, args[1:], plan)