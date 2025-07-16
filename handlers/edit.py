from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from models.db import get_connection
from telegram.ext import CommandHandler, CallbackQueryHandler, ConversationHandler
from models.alert import (
    get_price_alerts, get_percent_alerts, get_volume_alerts, get_risk_alerts, get_custom_alerts,
    get_price_alert_by_id, get_percent_alert_by_id, get_volume_alert_by_id,
    get_risk_alert_by_id, get_custom_alert_by_id
)

SELECT_ALERT_TYPE, SELECT_ALERT_ID, CONFIRM_EDIT = range(3)

ALERT_TYPES = {
    "price": (get_price_alerts, "#P", "💰 Price Alerts"),
    "percent": (get_percent_alerts, "#%", "📉 Percent Alerts"),
    "volume": (get_volume_alerts, "#V", "📊 Volume Alerts"),
    "risk": (get_risk_alerts, "#R", "🛡 Risk Alerts"),
    "custom": (get_custom_alerts, "#C", "🧠 Custom Alerts"),
}


async def edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💰 Price", callback_data="edit_type|price")],
        [InlineKeyboardButton("📉 Percent", callback_data="edit_type|percent")],
        [InlineKeyboardButton("📊 Volume", callback_data="edit_type|volume")],
        [InlineKeyboardButton("🛡 Risk", callback_data="edit_type|risk")],
        [InlineKeyboardButton("🧠 Custom", callback_data="edit_type|custom")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_edit")]
    ]
    await update.message.reply_text(
        "🔧 *Edit Alert Type:*\nChoose which type of alert you'd like to edit:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_ALERT_TYPE


async def select_alert_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    alert_type = query.data.split("|")[1]
    context.user_data["edit_type"] = alert_type

    user_id = query.from_user.id
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT plan FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row or row[0] == "free":
        await query.edit_message_text(
            "⚠️ *Editing alerts is a Pro-only feature.*\nUse /upgrade@EliteTradeSignalBot to unlock it.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    await query.edit_message_text("🔍 Fetching your alerts...")
    return SELECT_ALERT_ID


async def show_alerts_for_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    alert_type = context.user_data.get("edit_type")
    user_id = query.from_user.id

    fetch_fn, prefix, label = ALERT_TYPES[alert_type]
    alerts = fetch_fn(user_id)

    if not alerts:
        await query.edit_message_text(f"❌ No {label.lower()} to edit.")
        return ConversationHandler.END

    buttons = []
    for row in alerts:
        alert_id = row[0]
        summary = summarize_alert(alert_type, row)
        buttons.append([
            InlineKeyboardButton(f"{prefix}-{alert_id}: {summary}", callback_data=f"select_edit|{alert_type}|{alert_id}")
        ])

    keyboard = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(
        text=f"✏️ *Select an alert to edit ({label}):*\n_Updated: {datetime.now().strftime('%H:%M:%S')}_",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    return SELECT_ALERT_ID


def summarize_alert(alert_type, row):
    if alert_type == "price":
        _, symbol, cond, target, repeat = row
        return f"{symbol} {cond} {target} {'🔁' if repeat else ''}"
    elif alert_type == "percent":
        _, symbol, base, threshold, repeat = row
        return f"{symbol} ±{threshold}% from ${base:.2f} {'🔁' if repeat else ''}"
    elif alert_type == "volume":
        _, symbol, tf, mult, repeat = row
        return f"{symbol} > {mult}x volume ({tf}) {'🔁' if repeat else ''}"
    elif alert_type == "risk":
        _, symbol, sl, tp, repeat = row
        return f"{symbol} SL: {sl} / TP: {tp} {'🔁' if repeat else ''}"
    elif alert_type == "custom":
        _, symbol, p_cond, p_val, r_cond, r_val, repeat = row
        rsi_part = f"{r_cond.upper()} {r_val}" if r_val is not None else r_cond.upper()
        return f"{symbol} Price {p_cond} {p_val} & {rsi_part} {'🔁' if repeat else ''}"
    return ""


async def show_alert_for_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, alert_type, alert_id = query.data.split("|")
    alert_id = int(alert_id)
    user_id = query.from_user.id

    context.user_data["edit_alert"] = {"type": alert_type, "id": alert_id}

    # Fetch alert by type
    if alert_type == "price":
        row = get_price_alert_by_id(user_id, alert_id)
        alert_text = f"{row[1]} {row[2]} {row[3]} {'🔁' if row[4] else ''}"
    elif alert_type == "percent":
        row = get_percent_alert_by_id(user_id, alert_id)
        alert_text = f"{row[1]} ±{row[3]}% from ${row[2]:.2f} {'🔁' if row[4] else ''}"
    elif alert_type == "volume":
        row = get_volume_alert_by_id(user_id, alert_id)
        alert_text = f"{row[1]} volume > {row[3]}x avg ({row[2]}) {'🔁' if row[4] else ''}"
    elif alert_type == "risk":
        row = get_risk_alert_by_id(user_id, alert_id)
        alert_text = f"{row[1]} SL: {row[2]} / TP: {row[3]} {'🔁' if row[4] else ''}"
    elif alert_type == "custom":
        row = get_custom_alert_by_id(user_id, alert_id)
        rsi_display = f"{row[5].upper()} {row[6]}" if row[6] is not None else row[5].upper()
        alert_text = f"{row[1]} Price {row[2]} {row[3]} & {rsi_display} {'🔁' if row[7] else ''}"
    else:
        await query.edit_message_text("❌ Unknown alert type.")
        return ConversationHandler.END

    # Display final message with confirm/cancel
    msg = f"🛠 *Editing Alert #{alert_type[0].upper()}-{alert_id}*\n\n`{alert_text.strip()}`"
    keyboard = [
        [InlineKeyboardButton("✅ Confirm Edit", callback_data="confirm_edit")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_edit")]
    ]
    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return CONFIRM_EDIT
    
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from models.alert import (
    delete_price_alert, delete_percent_alert, delete_volume_alert,
    delete_risk_alert, delete_custom_alert
)

async def confirm_edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    alert = context.user_data.get("edit_alert")
    if not alert:
        await query.edit_message_text("⚠️ Something went wrong. No alert selected.")
        return ConversationHandler.END

    user_id = query.from_user.id
    alert_type = alert["type"]
    alert_id = alert["id"]

    # Delete old alert
    if alert_type == "price":
        delete_price_alert(user_id, alert_id)
    elif alert_type == "percent":
        delete_percent_alert(user_id, alert_id)
    elif alert_type == "volume":
        delete_volume_alert(user_id, alert_id)
    elif alert_type == "risk":
        delete_risk_alert(user_id, alert_id)
    elif alert_type == "custom":
        delete_custom_alert(user_id, alert_id)

    # Notify user and trigger the alert creation flow
    await query.edit_message_text(
        "✅ Old alert deleted.\nLet's recreate it now — follow the steps.",
        parse_mode="Markdown"
    )

    # Simulate starting the /addalert process
    from handlers.alert_handlers import start_price_alert, start_percent_alert, start_volume_alert, start_risk_alert, start_custom_alert

    # Re-use alert creation flow based on type
    if alert_type == "price":
        return await start_price_alert(update, context)
    elif alert_type == "percent":
        return await start_percent_alert(update, context)
    elif alert_type == "volume":
        return await start_volume_alert(update, context)
    elif alert_type == "risk":
        return await start_risk_alert(update, context)
    elif alert_type == "custom":
        return await start_custom_alert(update, context)

    return ConversationHandler.END
    
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

async def cancel_edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Optional: clear any edit-related data
    context.user_data.pop("edit_alert", None)
    context.user_data.pop("edit_type", None)
    context.user_data.pop("edit_alert_type", None)

    await query.edit_message_text("❌ Edit cancelled.")
    return ConversationHandler.END
    
    
edit_conv = ConversationHandler(
        entry_points=[CommandHandler("edit", edit_start)],
        states={
            SELECT_ALERT_TYPE: [
                CallbackQueryHandler(select_alert_type, pattern="^edit_type\|")
            ],
            SELECT_ALERT_ID: [
                CallbackQueryHandler(show_alerts_for_edit)
            ],
            CONFIRM_EDIT: [
                CallbackQueryHandler(show_alert_for_edit, pattern="^select_edit\|"),
                CallbackQueryHandler(confirm_edit_callback, pattern="^confirm_edit$"),
                CallbackQueryHandler(cancel_edit_callback, pattern="^cancel_edit$")  # ✅ Add here
            ]
        },
        fallbacks=[
        CallbackQueryHandler(cancel_edit_callback, pattern="^cancel_edit$")  # ✅ Add properly here
        ],
        per_message=False
    )