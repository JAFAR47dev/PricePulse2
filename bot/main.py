import os
import sys
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ApplicationBuilder
)

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from handlers import register_all_handlers
from dotenv import load_dotenv
from models.db import init_db
from services.alert_service import start_alert_checker
from tasks.models import create_referrals_table, create_task_progress_table
from tasks.handlers import tasks_menu, handle_task_buttons, receive_proof
from tasks.review_tasks import review_tasks
from tasks.check_expiry import check_expired_pro_users
from tasks.admin_approval import handle_task_review_callback
from stats.handlers import show_stats
from services.alert_service import run_ai_strategy_checker
from services.wallet_monitor import monitor_wallets

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Filters for task proofs
proof_filter = (
    (filters.TEXT & filters.Regex(r"^\s*[1-3]\s*[:：]")) |
    (filters.PHOTO & filters.CaptionRegex(r"^\s*[1-3]\s*$")) |
    (filters.Document.ALL & filters.CaptionRegex(r"^\s*[1-3]\s*$"))
)

# ✅ Startup logs
print("🚀 Bot running...")

# ✅ Hook for background task (wallet monitoring)
async def post_init(application):
    application.create_task(monitor_wallets(application.bot))

# ✅ Main function
def main():
    init_db()
    create_referrals_table()
    create_task_progress_table()

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(post_init)  # Register wallet monitor task here
        .build()
    )

    register_all_handlers(app)

    # Standard command handlers
    app.add_handler(CommandHandler("tasks", tasks_menu))
    app.add_handler(CommandHandler("stats", show_stats))
    app.add_handler(CallbackQueryHandler(handle_task_buttons, pattern="^(submit_proof|check_status)$"))
    app.add_handler(CommandHandler("reviewtasks", review_tasks))
    app.add_handler(MessageHandler(proof_filter, receive_proof))
    app.add_handler(CallbackQueryHandler(handle_task_review_callback, pattern=r"^(approve_task|reject_task)\|\d+\|\d+$"))

    # ⏱️ Auto-downgrade expired Pro users
    app.job_queue.run_repeating(check_expired_pro_users, interval=43200, first=10)

    # ✅ AI Strategy Checker (every 5 minutes)
    app.job_queue.run_repeating(run_ai_strategy_checker, interval=300, first=15)

    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()