import os
import sys
from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, ContextTypes, filters
)

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
from models.db import init_db
from services.alert_service import start_alert_checker
from handlers.general import register_general_handlers
from handlers.price_handlers import register_price_handlers
from handlers.alert_handlers import register_alert_handlers
from handlers.chart import show_chart
from handlers.portfolio import (
    view_portfolio, remove_asset, clear_portfolio,
    set_portfolio_loss_limit, set_portfolio_profit_target
)
from handlers.admin import set_plan, pro_user_list
from handlers.upgrade import (
    upgrade_menu, handle_plan_selection, back_to_plans,
    show_payment_instructions, confirm_payment
)
from tasks.models import create_referrals_table, create_task_progress_table
from tasks.handlers import tasks_menu, handle_task_buttons, receive_proof
from tasks.review_tasks import review_tasks
from tasks.check_expiry import check_expired_pro_users
from tasks.admin_approval import handle_task_review_callback
from stats.handlers import show_stats

# Load .env
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Filters for task proofs
proof_filter = (
    (filters.TEXT & filters.Regex(r"^\s*[1-3]\s*[:：]")) |
    (filters.PHOTO & filters.CaptionRegex(r"^\s*[1-3]\s*$")) |
    (filters.Document.ALL & filters.CaptionRegex(r"^\s*[1-3]\s*$"))
)

# Set bot commands for BotFather
from telegram import BotCommandScopeDefault

async def set_bot_commands(app):
    await app.bot.set_my_commands([
        BotCommand("upgrade", "View Pro benefits and plans"),
        BotCommand("tasks", "Complete tasks for free Pro access"),
        BotCommand("stats", "View global usage stats"),
        BotCommand("prolist", "Admin: View Pro users"),
        BotCommand("chart", "View coin chart"),
        BotCommand("portfolio", "View your portfolio"),
        BotCommand("removeasset", "Remove a portfolio asset"),
        BotCommand("portfoliolimit", "Set loss threshold"),
        BotCommand("portfoliotarget", "Set profit target"),
        BotCommand("clearportfolio", "Clear your portfolio"),
        BotCommand("setplan", "Admin: Manually set user plan"),
        BotCommand("reviewtasks", "Admin: Approve/reject tasks")
    ], scope=BotCommandScopeDefault())
    print("✅ Bot commands set (Default scope)")

# Startup jobs
async def on_startup(app):
    print("🚀 Bot starting...")
    start_alert_checker(app.job_queue)

def main():
    init_db()
    create_referrals_table()
    create_task_progress_table()

    app = ApplicationBuilder().token(TOKEN).post_init(on_startup).post_init(set_bot_commands).build()

    # Register command modules
    register_price_handlers(app)
    register_alert_handlers(app)
    register_general_handlers(app)

    # Core commands (private only)
    app.add_handler(CommandHandler("upgrade", upgrade_menu, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("tasks", tasks_menu, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("stats", show_stats, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("prolist", pro_user_list, filters=filters.ChatType.PRIVATE))

    # Upgrade/payment flow
    app.add_handler(CallbackQueryHandler(handle_plan_selection, pattern=r"^plan_(monthly|yearly|lifetime)$"))
    app.add_handler(CallbackQueryHandler(show_payment_instructions, pattern=r"^pay_(monthly|yearly|lifetime)_(usdt|ton|btc)$"))
    app.add_handler(CallbackQueryHandler(back_to_plans, pattern="^back_to_plans$"))
    app.add_handler(CallbackQueryHandler(handle_plan_selection, pattern=r"^back_to_crypto_(monthly|yearly|lifetime)$"))
    app.add_handler(CallbackQueryHandler(confirm_payment, pattern=r"^confirm_(monthly|yearly|lifetime)_(usdt|ton|btc)$"))

    # Portfolio tools
    app.add_handler(CommandHandler("chart", show_chart))
    app.add_handler(CommandHandler("portfolio", view_portfolio))
    app.add_handler(CommandHandler("removeasset", remove_asset))
    app.add_handler(CommandHandler("portfoliolimit", set_portfolio_loss_limit))
    app.add_handler(CommandHandler("portfoliotarget", set_portfolio_profit_target))
    app.add_handler(CommandHandler("clearportfolio", clear_portfolio))

    # Task & admin commands
    app.add_handler(CommandHandler("setplan", set_plan))
    app.add_handler(CallbackQueryHandler(handle_task_buttons, pattern="^(submit_proof|check_status)$"))
    app.add_handler(CommandHandler("reviewtasks", review_tasks))
    app.add_handler(MessageHandler(proof_filter, receive_proof))
    app.add_handler(CallbackQueryHandler(handle_task_review_callback, pattern=r"^(approve_task|reject_task)\|\d+\|\d+$"))

    # Backup: fallback for command input (for bots with missing BotFather config)
    async def fallback_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return
        text = update.message.text.strip().lower()
        if text.startswith("/upgrade"):
            await upgrade_menu(update, context)
        elif text.startswith("/tasks"):
            await tasks_menu(update, context)
        elif text.startswith("/prolist"):
            await pro_user_list(update, context)
        elif text.startswith("/stats"):
            await show_stats(update, context)

    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^/"), fallback_command_handler))

    # Run recurring jobs
    app.job_queue.run_repeating(check_expired_pro_users, interval=43200, first=10)

    # ✅ Start bot using polling (free on Render)
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
