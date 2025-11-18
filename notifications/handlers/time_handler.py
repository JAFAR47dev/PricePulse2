from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes
from utils.timezone_utils import convert_to_local_time
from notifications.models import get_user_notification_settings, update_user_notification_setting

MORNING = ["06:00", "07:00", "08:00", "09:00", "10:00", "11:00"]
EVENING = ["18:00", "19:00", "20:00", "21:00", "22:00", "23:00"]


async def refresh_notify_menu(update, context):
    """Refresh notify menu"""
    from notifications.handlers.notify_menu import notify_command
    return await notify_command(update, context)


def build_keyboard(options, prefix):
    rows = []
    for i in range(0, len(options), 3):
        row = [
            InlineKeyboardButton(t, callback_data=f"{prefix}{t}")
            for t in options[i:i+3]
        ]
        rows.append(row)

    # ✅ back button
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="notify_time_back")])
    return rows


async def time_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = build_keyboard(MORNING, "notify_time_morning_")
    await query.message.edit_text(
        "⏰ *Select Morning Notification Time:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def apply_morning_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    picked = query.data.replace("notify_time_morning_", "")

    settings = get_user_notification_settings(user_id)
    user_tz = settings.get("timezone") or "UTC"

    try:
        local_time = convert_to_local_time(user_tz, picked)
    except:
        local_time = picked

    update_user_notification_setting(user_id, "morning_time", local_time)

    # if twice, ask for evening
    if settings["frequency"] == "twice":
        keyboard = build_keyboard(EVENING, "notify_time_evening_")
        return await query.message.edit_text(
            f"✅ Morning time set: *{local_time}*\n\nNow select *Evening Time*: ",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    # once-daily → finish
    return await refresh_notify_menu(update, context)


async def apply_evening_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("✅ Evening time saved.")

    user_id = query.from_user.id
    picked = query.data.replace("notify_time_evening_", "")

    settings = get_user_notification_settings(user_id)
    user_tz = settings.get("timezone") or "UTC"

    try:
        local_time = convert_to_local_time(user_tz, picked)
    except:
        local_time = picked

    update_user_notification_setting(user_id, "evening_time", local_time)

    return await refresh_notify_menu(update, context)


async def handle_back_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    return await refresh_notify_menu(update, context)


def register_time_handlers(app):
    app.add_handler(CallbackQueryHandler(time_menu_handler, pattern="^notify_time_menu$"))
    app.add_handler(CallbackQueryHandler(apply_morning_time, pattern="^notify_time_morning_"))
    app.add_handler(CallbackQueryHandler(apply_evening_time, pattern="^notify_time_evening_"))
    app.add_handler(CallbackQueryHandler(handle_back_button, pattern="^notify_time_back$"))