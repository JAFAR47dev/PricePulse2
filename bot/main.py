import os
import sys
import asyncio
import nest_asyncio
nest_asyncio.apply()

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
from handlers.fallback_handler import fallback_command_handler
from handlers.daily_coin import coin_of_the_day
from handlers.calendar import calendar_command
from handlers.heatmap import heatmap_command
from handlers.convert import convert_command
from handlers.learn import learn_command, learn_term_callback, learn_page_callback
from handlers.markets import markets_command
from handlers.compare import compare_command
from handlers.links import links_command
from handlers.gasfees import gasfees_command
from handlers.funfact import funfact_command

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

proof_filter = (
    (filters.TEXT & filters.Regex(r"^\s*[1-3]\s*[:：]")) |
    (filters.PHOTO & filters.CaptionRegex(r"^\s*[1-3]\s*$")) |
    (filters.Document.ALL & filters.CaptionRegex(r"^\s*[1-3]\s*$"))
)

# ✅ Main async function
async def main():
    init_db()
    create_referrals_table()
    create_task_progress_table()

    app = ApplicationBuilder().token(TOKEN).build()

    # Register grouped handler modules
    register_price_handlers(app)
    register_alert_handlers(app)
    register_general_handlers(app)
    app.add_handler(CommandHandler("cod", coin_of_the_day))
    app.add_handler(CommandHandler("calendar", calendar_command))
    app.add_handler(CommandHandler("heatmap", heatmap_command))
    app.add_handler(CommandHandler("convert", convert_command))
    app.add_handler(CommandHandler("learn", learn_command))
    app.add_handler(CallbackQueryHandler(learn_term_callback, pattern=r"^learn_\d+$"))
    app.add_handler(CallbackQueryHandler(learn_page_callback, pattern=r"^learn_page_\d+$"))
    app.add_handler(CommandHandler("markets", markets_command))
    app.add_handler(CommandHandler("compare", compare_command))
    app.add_handler(CommandHandler("links", links_command))
    app.add_handler(CommandHandler("gasfees", gasfees_command))
    app.add_handler(CommandHandler("funfact", funfact_command))app.add_handler(CommandHandler("funfact", funfact_command))

    # Standard command handlers
    app.add_handler(CommandHandler("upgrade", upgrade_menu))
    app.add_handler(CommandHandler("tasks", tasks_menu))
    app.add_handler(CommandHandler("stats", show_stats))
    app.add_handler(CommandHandler("prolist", pro_user_list))

    # Payment flow
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

    # Admin + task moderation
    app.add_handler(CommandHandler("setplan", set_plan))
    app.add_handler(CallbackQueryHandler(handle_task_buttons, pattern="^(submit_proof|check_status)$"))
    app.add_handler(CommandHandler("reviewtasks", review_tasks))
    app.add_handler(MessageHandler(proof_filter, receive_proof))
    app.add_handler(CallbackQueryHandler(handle_task_review_callback, pattern=r"^(approve_task|reject_task)\|\d+\|\d+$"))

    # Final fallback
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"^/"), fallback_command_handler))

    # Start bot
    print("🚀 Bot starting...")
    start_alert_checker(app.job_queue)
    app.job_queue.run_repeating(check_expired_pro_users, interval=43200, first=10)
    await app.run_polling()
# ✅ Entry point
if __name__ == '__main__':
    asyncio.run(main())