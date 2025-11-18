# utils/private_guard_manager.py

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

# ✅ List of private-only commands
PRIVATE_ONLY_COMMANDS = [
    "set", "alerts", "remove", "removeall",
    "watch", "watchlist", "removewatch",
    "portfolio", "addasset", "removeasset",
    "clearportfolio", "portfoliolimit",
    "portfoliotarget", "prediction", "aistrat",
    "aiscan", "bt", "screen", "track", "untrack",
    "mywhales", "tasks", "referral", "upgrade"
]

# ✅ Guard function: blocks private-only commands in groups
async def private_command_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.effective_chat.type
    if chat_type in ["group", "supergroup"]:
        await update.message.reply_text(
            "⚠️ This command can only be used in private chat.\n"
            "Please DM me instead → [Start Chat](https://t.me/EliteTradeSignalBot)",
            disable_web_page_preview=True,
            parse_mode="Markdown"
        )
        return True
    return False


# ✅ Function to wrap handlers for private-only restriction
def apply_private_command_restrictions(app):
    """
    Iterates over registered handlers and wraps private-only ones
    with a guard that blocks them in group chats.
    """
    def wrap_private_only(handler_func):
        async def wrapper(update, context):
            if await private_command_guard(update, context):
                return
            await handler_func(update, context)
        return wrapper

    # Avoid crash if handler group 0 doesn’t exist yet
    if 0 in app.handlers:
        for cmd in PRIVATE_ONLY_COMMANDS:
            for handler in app.handlers[0]:
                if isinstance(handler, CommandHandler) and cmd in handler.commands:
                    handler.callback = wrap_private_only(handler.callback)