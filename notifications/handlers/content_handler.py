from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes, ConversationHandler

from notifications.models import get_user_notification_settings, update_user_notification_setting


async def refresh_notify_menu(update, context):
    """Return to main notify settings menu."""
    from notifications.handlers.notify_menu import notify_command
    return await notify_command(update, context)


def build_content_keyboard(settings: dict):
    """Create inline checkboxes menu based on user's DB values."""

    def check(val): return "✅" if val else "❌"

    keyboard = [
        [InlineKeyboardButton(f"{check(settings['include_global'])} Global Market",
                              callback_data="toggle_global")],
        [InlineKeyboardButton(f"{check(settings['include_gainers'])} Top Gainers",
                              callback_data="toggle_gainers")],
        [InlineKeyboardButton(f"{check(settings['include_losers'])} Top Losers",
                              callback_data="toggle_losers")],
        [InlineKeyboardButton(f"{check(settings['include_news'])} Crypto News",
                              callback_data="toggle_news")],
        [InlineKeyboardButton(f"{check(settings['include_gas'])} Gas Fees",
                              callback_data="toggle_gas")],
        [InlineKeyboardButton(f"{check(settings['include_cod'])} Coin of Day",
                              callback_data="toggle_cod")],

        [InlineKeyboardButton("⬅ Back", callback_data="notify_content_back")],
    ]

    return InlineKeyboardMarkup(keyboard)


async def content_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User clicked Content Customization → show menu."""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    # BACK handling
    if data == "notify_content_back":
        from notifications.handlers.notify_menu import notify_command
        return await notify_command(update, context)

    settings = get_user_notification_settings(user_id)

    await query.edit_message_text(
        "📰 *Customize Notification Content*\n"
        "Tap to toggle ON/OFF:",
        parse_mode="Markdown",
        reply_markup=build_content_keyboard(settings)
    )

async def toggle_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User tapped a checkbox."""
    query = update.callback_query
    user_id = query.from_user.id
    action = query.data.replace("toggle_", "")

    column = f"include_{action}"

    # Toggle DB value
    settings = get_user_notification_settings(user_id)
    current_val = settings[column]
    update_user_notification_setting(user_id, column, 0 if current_val else 1)

    # Reload updated settings
    settings = get_user_notification_settings(user_id)

    await query.edit_message_text(
        "📰 *Customize Notification Content*\n"
        "Tap to toggle ON/OFF:",
        parse_mode="Markdown",
        reply_markup=build_content_keyboard(settings)
    )
    
def register_content_handlers(app):
    app.add_handler(CallbackQueryHandler(content_menu_handler, pattern="^notify_content_menu$"))
    app.add_handler(CallbackQueryHandler(content_menu_handler, pattern="^notify_content_back$"))
    app.add_handler(CallbackQueryHandler(toggle_content, pattern="^toggle_"))