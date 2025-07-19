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
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g., https://your-app.onrender.com

# Filters for task proofs
proof_filter = (
    (filters.TEXT & filters.Regex(r"^\s*[1-3]\s*[:：]")) |
    (filters.PHOTO & filters.CaptionRegex(r"^\s*[1-3]\s*$")) |
    (filters.Document.ALL & filters.CaptionRegex(r"^\s*[1-3]\s*$"))
)

# ✅ Startup logs
print("🚀 Bot starting with webhook...")

# ✅ Background task for wallet monitoring
async def post_init(application):
    application.create_task(monitor_wallets(application.bot))

def main():
    init_db()
    create_referrals_table()
    create_task_progress_table()

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    register_all_handlers(app)

    app.add_handler(CommandHandler("tasks", tasks_menu))
    app.add_handler(CommandHandler("stats", show_stats))
    app.add_handler(CallbackQueryHandler(handle_task_buttons, pattern="^(submit_proof|check_status)$"))
    app.add_handler(CommandHandler("reviewtasks", review_tasks))
    app.add_handler(MessageHandler(proof_filter, receive_proof))
    app.add_handler(CallbackQueryHandler(handle_task_review_callback, pattern=r"^(approve_task|reject_task)\|\d+\|\d+$"))

    # Jobs
    app.job_queue.run_repeating(check_expired_pro_users, interval=43200, first=10)
    app.job_queue.run_repeating(run_ai_strategy_checker, interval=300, first=15)

    # ✅ Start webhook
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),  # Render will detect this
        webhook_url=WEBHOOK_URL,
        drop_pending_updates=True,
    )

if __name__ == '__main__':
    main()