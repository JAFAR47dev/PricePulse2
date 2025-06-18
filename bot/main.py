import os
import sys
from telegram import Update
from telegram.ext import ContextTypes
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
from aiohttp import web
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from models.db import init_db
from handlers.general import register_general_handlers
from handlers.price_handlers import register_price_handlers
from handlers.alert_handlers import register_alert_handlers
from services.alert_service import start_alert_checker
from handlers.chart import show_chart
from handlers.admin import set_plan, pro_user_list
from handlers.portfolio import view_portfolio, remove_asset, clear_portfolio, set_portfolio_loss_limit, set_portfolio_profit_target
from tasks.models import create_referrals_table, create_task_progress_table
from tasks.handlers import tasks_menu, handle_task_buttons, receive_proof
from tasks.review_tasks import review_tasks
from tasks.check_expiry import check_expired_pro_users
from tasks.admin_approval import handle_task_review_callback
from stats.handlers import show_stats
from handlers.upgrade import (
    upgrade_menu,
    handle_plan_selection,
    back_to_plans,
    show_payment_instructions,
    confirm_payment
)

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Example: https://your-app.onrender.com/webhook

# Filters for /tasks
proof_filter = (
    (filters.TEXT & filters.Regex(r"^\s*[1-3]\s*[:：]")) |
    (filters.PHOTO & filters.CaptionRegex(r"^\s*[1-3]\s*$")) |
    (filters.Document.ALL & filters.CaptionRegex(r"^\s*[1-3]\s*$"))
)

async def on_startup(app):
    print("🚀 Bot starting...")
    start_alert_checker(app.job_queue)
    await app.bot.set_webhook(WEBHOOK_URL)

# --- Webhook route for Telegram ---
async def telegram_webhook(request):
    data = await request.json()
    await app.update_queue.put(data)
    return web.Response(text="OK")

# --- Set up and start app ---
init_db()
create_referrals_table()
create_task_progress_table()

app = ApplicationBuilder().token(TOKEN).post_init(on_startup).build()

register_price_handlers(app)
register_alert_handlers(app)
register_general_handlers(app)

# Command Handlers
app.add_handler(CommandHandler("upgrade", upgrade_menu))
app.add_handler(CommandHandler("prolist", pro_user_list))
app.add_handler(CommandHandler("stats", show_stats))
app.add_handler(CommandHandler("chart", show_chart))
app.add_handler(CommandHandler("portfolio", view_portfolio))
app.add_handler(CommandHandler("removeasset", remove_asset))
app.add_handler(CommandHandler("portfoliolimit", set_portfolio_loss_limit))
app.add_handler(CommandHandler("portfoliotarget", set_portfolio_profit_target))
app.add_handler(CommandHandler("clearportfolio", clear_portfolio))
app.add_handler(CommandHandler("setplan", set_plan))
app.add_handler(CommandHandler("tasks", tasks_menu))
app.add_handler(CommandHandler("reviewtasks", review_tasks))

# CallbackQuery Handlers
app.add_handler(CallbackQueryHandler(handle_plan_selection, pattern=r"^plan_(monthly|yearly|lifetime)$"))
app.add_handler(CallbackQueryHandler(show_payment_instructions, pattern=r"^pay_(monthly|yearly|lifetime)_(usdt|ton|btc)$"))
app.add_handler(CallbackQueryHandler(back_to_plans, pattern="^back_to_plans$"))
app.add_handler(CallbackQueryHandler(handle_plan_selection, pattern=r"^back_to_crypto_(monthly|yearly|lifetime)$"))
app.add_handler(CallbackQueryHandler(confirm_payment, pattern=r"^confirm_(monthly|yearly|lifetime)_(usdt|ton|btc)$"))
app.add_handler(CallbackQueryHandler(handle_task_buttons, pattern="^(submit_proof|check_status)$"))
app.add_handler(CallbackQueryHandler(handle_task_review_callback, pattern=r"^(approve_task|reject_task)\|\d+\|\d+$"))

# Message Handler for task proofs
app.add_handler(MessageHandler(proof_filter, receive_proof))

# Task check cron
app.job_queue.run_repeating(check_expired_pro_users, interval=43200, first=10)

# --- aiohttp Web App ---
web_app = web.Application()
web_app.router.add_post("/webhook", telegram_webhook)

if __name__ == "__main__":
    web.run_app(web_app, port=int(os.environ.get("PORT", 8080)))
