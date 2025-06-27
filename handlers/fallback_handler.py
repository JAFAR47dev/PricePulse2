# handlers/fallback_handler.py
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

async def fallback_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip().lower()
    user_message = update.message
    bot_username = (await context.bot.get_me()).username

    fallback_commands = {
        "/upgrade": "Upgrade to Pro",
        "/tasks": "Complete tasks for Pro",
        "/stats": "Bot statistics",
        "/prolist": "Admin-only user list"
    }

    for cmd, label in fallback_commands.items():
        if text.startswith(cmd):
            await context.bot.send_message(
                chat_id=user_message.chat_id,
                text=(
                    f"⚠️ It looks like `{cmd}` didn’t work properly.\n\n"
                    f"👉 Try this instead: [/{cmd[1:]}@{bot_username}](https://t.me/{bot_username}?start={cmd[1:]})"
                ),
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
            return

    await user_message.reply_text("❓ Unrecognized command. Try /start or /help.")