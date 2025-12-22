import os
import sys
import asyncio
import logging
import warnings
from dotenv import load_dotenv
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# --- Logging config: keep libraries quiet, show only relevant bot info ---
# Default to WARNING for noisy libraries
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.WARNING
)

# Create a small logger for your bot that we allow to print INFO
logger = logging.getLogger("bot")
logger.setLevel(logging.INFO)

# Suppress specific warning messages that python-telegram-bot prints and APScheduler tentative job info.
# We match by message substring so other warnings still appear.
warnings.filterwarnings("ignore", message="If 'per_message=False'")
warnings.filterwarnings("ignore", message="Adding job tentatively")
# (Optional) suppress PTBUserWarning if available as a class:
try:
    from telegram import PTBUserWarning  # may not exist in all PTB builds
    warnings.filterwarnings("ignore", category=PTBUserWarning)
except Exception:
    pass

# === Ensure import path ===
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# === Local imports ===
from handlers import register_all_handlers
from tasks.check_expiry import check_expired_pro_users
from tasks.models import create_referrals_table, create_task_progress_table
from db.migrations import init_db
from models.analytics_table import init_analytics_tables
from services.alert_service import start_alert_checker, run_ai_strategy_checker
from services.refresh_tokens import refresh_top_tokens
from services.refresh_whales import refresh_all_whales
from whales.whale_monitor import start_monitor
from services.refresh_coingecko_ids import refresh_coingecko_ids
from models.user_activity import update_last_active
from utils.private_guard_manager import apply_private_command_restrictions
from notifications.models import create_notifications_table
from notifications.scheduler import start_scheduler, stop_scheduler
from handlers.fav.utils.db_favorites import init_favorites_table

# === Load environment ===
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN missing in .env file")


async def post_init(application):
    """
    Called after the application is initialized.
    Perfect place to start the notification scheduler.
    """
    try:
        logger.info("🔧 Initializing post-startup tasks...")
        start_scheduler(application)
        logger.info("✅ Notification scheduler started successfully")
    except Exception as e:
        logger.error(f"❌ Failed to start notification scheduler: {e}")


async def post_shutdown(application):
    """
    Called before the application shuts down.
    Ensures graceful shutdown of the notification scheduler.
    """
    try:
        logger.info("🛑 Shutting down notification scheduler...")
        stop_scheduler()
        logger.info("✅ Notification scheduler stopped successfully")
    except Exception as e:
        logger.error(f"❌ Error stopping notification scheduler: {e}")


def main():
    # Initialize database tables
    init_db()
    init_analytics_tables() 
    init_favorites_table()
    create_referrals_table()
    create_task_progress_table()
    create_notifications_table()
    
    logger.info("✅ Database tables initialized")

    # Build application with lifecycle hooks
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    logger.info("✅ Application created with lifecycle hooks")

    # Register all command handlers
    register_all_handlers(app)
    apply_private_command_restrictions(app)
    logger.info("✅ Handlers registered")

    # Track user activity
    async def track_user_activity(update, context):
        user = update.effective_user
        if user:
            await asyncio.to_thread(update_last_active, user.id)

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, track_user_activity))
    app.add_handler(CallbackQueryHandler(track_user_activity))

    # === JOB QUEUE - BACKGROUND TASKS ===
    app.job_queue.run_repeating(check_expired_pro_users, interval=43200, first=10)
    app.job_queue.run_repeating(run_ai_strategy_checker, interval=300, first=600)
    app.job_queue.run_repeating(refresh_top_tokens, interval=604800, first=200)
    app.job_queue.run_repeating(refresh_all_whales, interval=604800, first=300)
    app.job_queue.run_repeating(start_monitor, interval=300, first=400)
    app.job_queue.run_repeating(refresh_coingecko_ids, interval=259200, first=150)
    
    # Start alert checker
    start_alert_checker(app.job_queue)
    logger.info("✅ Job queue tasks scheduled")

    logger.info("🤖 Bot is now running...")

    # ✅ FIX FOR PYTHON 3.12/3.13 THREAD LOOP BUG
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Start the bot with polling
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()