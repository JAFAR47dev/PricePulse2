from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext

from notifications.models import update_user_notification_setting


async def refresh_notify_menu(query, context):
    """Refresh the main notify menu after a setting change."""
    from notifications.handlers.notify_menu import notify_command
    # NOTE: notify_command needs update, so we call it like a command
    return await notify_command(query, context)


async def frequency_callback_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    # ✅ User opened frequency menu
    if data in ("notify_change_frequency", "notify_freq_menu"):
        keyboard = [
            [
                InlineKeyboardButton("Once a day", callback_data="notify_freq_once"),
                InlineKeyboardButton("Twice a day", callback_data="notify_freq_twice"),
            ],
            [
                InlineKeyboardButton("Turn Off", callback_data="notify_freq_off"),
            ],
            [
                InlineKeyboardButton("🔙 Back", callback_data="notify_freq_back")
            ]
        ]

        await query.edit_message_text(
            "🕒 *Choose Notification Frequency:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # ✅ Once
    if data == "notify_freq_once":
        update_user_notification_setting(user_id, "frequency", "once")
        await query.answer("✅ Frequency set to Once a day.")
        return await refresh_notify_menu(query, context)

    # ✅ Twice
    if data == "notify_freq_twice":
        update_user_notification_setting(user_id, "frequency", "twice")
        await query.answer("✅ Frequency set to Twice a day.")
        return await refresh_notify_menu(query, context)

    # ✅ Off
    if data == "notify_freq_off":
        update_user_notification_setting(user_id, "frequency", "off")
        await query.answer("✅ Notifications turned OFF.")
        return await refresh_notify_menu(query, context)

    # ✅ Back button
    if data == "notify_freq_back":
        return await refresh_notify_menu(update, context)