# services/signals_job.py
import asyncio
from telegram.ext import Application
from services.signal_data import fetch_top_100_indicator_data

# Job runs every 30 minutes
JOB_INTERVAL = 1800  # 30 minutes in seconds


async def run_indicator_fetch_job(context):
    """
    Background job that fetches indicator data for all 100 coins.
    Runs every 30 minutes to keep cache fresh.
    """
    print("[indicator_job] Starting scheduled indicator fetch...")
    try:
        results = await fetch_top_100_indicator_data(timeframe="1h", debug=False)
        print(f"[indicator_job] Fetch completed successfully - {len(results)} coins updated")
    except Exception as e:
        print(f"[indicator_job] Error during indicator fetch: {e}")


def setup_indicator_jobs(application: Application):
    """
    Set up the background job for indicator data fetching.
    Call this in your main bot initialization.
    """
    job_queue = application.job_queue
    
    # Run every 30 minutes, starting 60 seconds after bot starts
    # (giving bot time to fully initialize)
    job_queue.run_repeating(
        run_indicator_fetch_job,
        interval=JOB_INTERVAL,
        first=1800 # Start first run after 60 seconds
    )
    
    print(f"[indicator_job] Scheduled to run every {JOB_INTERVAL}s (30 minutes), first run in 60s")


async def force_indicator_fetch_now():
    """
    Manually trigger indicator fetch (useful for testing or admin commands).
    """
    print("[indicator_job] Manual indicator fetch triggered...")
    results = await fetch_top_100_indicator_data(timeframe="1h", debug=True)
    return results