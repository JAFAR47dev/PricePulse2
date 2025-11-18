from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler

from notifications.models import get_user_notification_settings
from notifications.handlers.delivery_handler import get_delivery_handler
from notifications.handlers.frequency_handler import frequency_callback_handler
from notifications.handlers.content_handler import register_content_handlers
from notifications.handlers.time_handler import register_time_handlers
from notifications.handlers.test_handler import test_callback_handler

def format_yes_no(value):
    return "✅" if value == 1 else "❌"


async def notify_callback_refresh(query, context):
    """Used by other menus to refresh this page without typing /notify."""
    return await notify_command(query, context)


async def notify_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    settings = get_user_notification_settings(user_id)

    text = (
        "📢 *Notification Settings*\n\n"
        f"• Frequency: *{settings['frequency']}*\n"
        f"• Delivery: *{settings['delivery']}*\n"
        f"• Morning Time: *{settings['morning_time']}*\n"
        f"• Evening Time: *{settings['evening_time']}*\n\n"
        "✅ *Included:*\n"
        f"- Global Market: {format_yes_no(settings['include_global'])}\n"
        f"- Top Gainers: {format_yes_no(settings['include_gainers'])}\n"
        f"- Top Losers: {format_yes_no(settings['include_losers'])}\n"
        f"- News: {format_yes_no(settings['include_news'])}\n"
        f"- Gas Fees: {format_yes_no(settings['include_gas'])}\n"
        f"- Coin of the Day: {format_yes_no(settings['include_cod'])}"
    )

    keyboard = [
        [
            InlineKeyboardButton("Change Frequency", callback_data="notify_change_frequency"),
            InlineKeyboardButton("Delivery Method", callback_data="notify_delivery_menu"),
        ],
        [
            InlineKeyboardButton("Customize Content", callback_data="notify_content_menu"),
            InlineKeyboardButton("Change Time", callback_data="notify_time_menu"),
        ],
        [InlineKeyboardButton("Send Test Notification", callback_data="notify_test")],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Normal command
    if update.message:
        return await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=reply_markup
        )

    # Callback refresh
    elif update.callback_query:
        query = update.callback_query
        await query.message.edit_text(
            text, parse_mode="Markdown", reply_markup=reply_markup
        )
        await query.answer()


def register_notify_handlers(app):
    app.add_handler(CommandHandler("notifications", notify_command))
    app.add_handler(get_delivery_handler())
    app.add_handler(CallbackQueryHandler(frequency_callback_handler, pattern="^notify_change_frequency|notify_freq_"))
    register_content_handlers(app)  
    register_time_handlers(app)
    app.add_handler(CallbackQueryHandler(test_callback_handler, pattern="^notify_test$"))