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

# --- Logging config ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.WARNING
)
logger = logging.getLogger("bot")
logger.setLevel(logging.INFO)

warnings.filterwarnings("ignore", message="If 'per_message=False'")
warnings.filterwarnings("ignore", message="Adding job tentatively")
try:
    from telegram import PTBUserWarning
    warnings.filterwarnings("ignore", category=PTBUserWarning)
except Exception:
    pass

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# === Local imports ===
from handlers import register_all_handlers
from tasks.check_expiry import check_expired_pro_users
from tasks.models import create_referrals_table, create_task_progress_table
from database.migrations import init_db
from models.analytics_table import init_analytics_tables
from services.alert_service import start_alert_checker
from services.refresh_tokens import refresh_top_tokens
from services.refresh_whales import refresh_all_whales
from whales.whale_monitor import start_monitor
from services.refresh_top200_coins import refresh_top200_coingecko_ids
from services.refresh_top100_coins import refresh_top100_coingecko_ids
from models.user_activity import update_last_active, cleanup_old_analytics
from utils.private_guard_manager import apply_private_command_restrictions
from notifications.models import create_notifications_table
from notifications.scheduler import start_scheduler, stop_scheduler
from handlers.fav.utils.db_favorites import init_favorites_table
from services.screener_job import setup_screener_jobs, force_precompute_priority_timeframes
from services.signals_job import setup_indicator_jobs
from services.movers_service import MoversService
from services.performance_tracker import PerformanceTracker
from models.user import get_users_expiring_in, trial_expiry_warning_job, trial_expiry_notification_job
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN missing in .env file")

# ============================================================================
# SINGLETON SERVICES
# ============================================================================
movers_service      = MoversService()
performance_tracker = PerformanceTracker()   # single instance reused everywhere
logger.info("✅ Movers service initialized")
logger.info("✅ Performance tracker initialized")


# ============================================================================
# BACKGROUND TASK — outcome resolution
# ============================================================================

async def _outcome_resolution_job(context):
    """
    PTB job-queue wrapper around resolve_pending_outcomes.
    Runs every 30 minutes via job_queue.run_repeating so it shares the
    application's event loop and is cancelled cleanly on shutdown.
    """
    try:
        resolved = await performance_tracker.resolve_pending_outcomes()
        if resolved:
            logger.info(f"✅ Outcome resolution: {resolved} setup(s) resolved")
    except Exception as e:
        logger.warning(f"⚠️  outcome_resolution_job error: {e}")


# ============================================================================
# LIFECYCLE HOOKS
# ============================================================================

async def post_init(application):
    try:
        logger.info("🔧 Initializing post-startup tasks...")
        start_scheduler(application)
        logger.info("✅ Notification scheduler started")
    except Exception as e:
        logger.error(f"❌ Failed to start notification scheduler: {e}")


async def post_shutdown(application):
    try:
        logger.info("🛑 Shutting down services...")
        stop_scheduler()
        logger.info("✅ Notification scheduler stopped")
        await movers_service.close()
        logger.info("✅ Movers service closed")
    except Exception as e:
        logger.error(f"❌ Error during shutdown: {e}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    # ── Database bootstrap ────────────────────────────────────────────
    init_db()
    init_analytics_tables()
    init_favorites_table()
    create_referrals_table()
    create_task_progress_table()
    create_notifications_table()
    # PerformanceTracker._ensure_schema() is called in __init__ above,
    # so trade_setups table already exists by this point.
    logger.info("✅ Database tables initialized")

    # ── Build application ─────────────────────────────────────────────
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    logger.info("✅ Application created")

    # ── Handlers ──────────────────────────────────────────────────────
    register_all_handlers(app)
    apply_private_command_restrictions(app)
    logger.info("✅ Handlers registered")

    # ── User activity tracking ────────────────────────────────────────
    async def track_user_activity(update, context):
        user = update.effective_user
        if user:
            await asyncio.to_thread(update_last_active, user.id)

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, track_user_activity))
    app.add_handler(CallbackQueryHandler(track_user_activity))

    # ── Job queue ─────────────────────────────────────────────────────
    jq = app.job_queue

    # Existing jobs (unchanged)
    jq.run_repeating(check_expired_pro_users,       interval=3600,   first=10)
    jq.run_repeating(refresh_top_tokens,            interval=604800, first=1800)
    jq.run_repeating(refresh_all_whales,            interval=604800, first=1500)
    jq.run_repeating(start_monitor,                 interval=300,    first=1200)
    jq.run_repeating(refresh_top200_coingecko_ids,  interval=259200, first=900)
    jq.run_repeating(refresh_top100_coingecko_ids,  interval=259200, first=600)
    jq.run_repeating(cleanup_old_analytics,         interval=86400,  first=15)
    jq.run_repeating(trial_expiry_warning_job,   interval=3600, first=60)
    jq.run_repeating(trial_expiry_notification_job, interval=3600, first=90)

    # Performance tracker — resolve setup outcomes every 30 minutes.
    # first=120 gives the bot 2 minutes to fully start before the first run.
    jq.run_repeating(_outcome_resolution_job, interval=1800, first=120)
    logger.info("✅ Performance tracker outcome-resolution job scheduled (every 30 min)")

    # Alert checker and screener
    start_alert_checker(jq)
    #setup_screener_jobs(app, use_parallel=False)
    logger.info("✅ Job queue tasks scheduled")

    logger.info("🤖 Bot is now running...")

    try:
        asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()