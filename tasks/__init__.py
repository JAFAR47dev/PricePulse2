from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, ContextTypes, filters
)

from .handlers import tasks_menu, claim_streak_reward


def register_task_handlers(app):
    
       app.add_handler(CommandHandler("tasks", tasks_menu))
       app.add_handler(CallbackQueryHandler(claim_streak_reward, pattern="claim_streak_reward"))