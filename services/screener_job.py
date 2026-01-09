# services/screener_job.py
import asyncio
from telegram.ext import Application
from services.screener_engine import precompute_all_coins, is_cache_fresh

# Job runs every 10 minutes
JOB_INTERVAL = 600  # 10 minutes in seconds


async def run_screener_precompute_job(context):
    """
    Background job that pre-fetches data for all 100 coins.
    Runs every 5 minutes to keep cache fresh.
    """
    print("[screener_job] Starting scheduled pre-computation...")
    try:
        await precompute_all_coins(timeframe="1h")
        print("[screener_job] Pre-computation completed successfully")
    except Exception as e:
        print(f"[screener_job] Error during pre-computation: {e}")


def setup_screener_jobs(application: Application):
    """
    Set up the background job for screener pre-computation.
    Call this in your main bot initialization.
    """
    job_queue = application.job_queue
    
    # Run every 5 minutes, starting 60 seconds after bot starts
    # (giving bot time to fully initialize)
    job_queue.run_repeating(
        run_screener_precompute_job,
        interval=JOB_INTERVAL,
        first=1200  # Start first run after 180 seconds
    )
    
    print(f"[screener_job] Scheduled to run every {JOB_INTERVAL}s (10 minutes), first run in 180s")


async def force_precompute_now():
    """
    Manually trigger pre-computation (useful for testing or admin commands).
    """
    print("[screener_job] Manual pre-computation triggered...")
    await precompute_all_coins(timeframe="1h")