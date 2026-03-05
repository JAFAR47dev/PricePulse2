# services/screener_job.py
import asyncio
from telegram.ext import Application
from services.screener_engine import precompute_all_coins, is_cache_fresh

# Job runs every 1 hour
JOB_INTERVAL = 3600  # 1 hour in seconds

# Priority timeframes warm up first (most commonly used)
PRIORITY_TIMEFRAMES = ["1h", "4h", "1d"]
ALL_TIMEFRAMES = ["5m", "15m", "30m", "1h", "4h", "1d"]


async def run_screener_precompute_job(context):
    """
    Scheduled job: refreshes all timeframe caches every hour.
    Skips timeframes that are still fresh.
    """
    print("[screener_job] Starting scheduled pre-computation for all timeframes...")

    for timeframe in ALL_TIMEFRAMES:
        try:
            if is_cache_fresh(timeframe, max_age_seconds=JOB_INTERVAL):
                print(f"[screener_job] Cache still fresh for {timeframe}, skipping...")
                continue

            print(f"[screener_job] Pre-computing {timeframe}...")
            await precompute_all_coins(timeframe=timeframe)
            print(f"[screener_job] Completed {timeframe}")

        except Exception as e:
            print(f"[screener_job] Error during pre-computation for {timeframe}: {e}")
            continue

    print("[screener_job] All timeframe pre-computations completed")


async def _startup_warmup():
    """
    Runs immediately at bot startup (as a background task).
    
    Phase 1: Warm up priority timeframes (1h, 4h, 1d) first — takes ~15 minutes.
             Users get live results for the most common timeframes quickly.
    Phase 2: Warm up remaining timeframes (5m, 15m, 30m) in the background.
    
    This ensures results are available within ~15 minutes of deploy,
    not 30+ minutes.
    """
    print("[screener_job] 🚀 Startup warmup started...")
    print(f"[screener_job] Phase 1: Warming priority timeframes: {PRIORITY_TIMEFRAMES}")

    # Phase 1 — priority timeframes first
    for tf in PRIORITY_TIMEFRAMES:
        try:
            print(f"[screener_job] Warming {tf}...")
            await precompute_all_coins(timeframe=tf)
            print(f"[screener_job] ✅ {tf} ready — users can now get live results")
        except Exception as e:
            print(f"[screener_job] ❌ Error warming {tf}: {e}")

    remaining = [tf for tf in ALL_TIMEFRAMES if tf not in PRIORITY_TIMEFRAMES]
    print(f"[screener_job] Phase 2: Warming remaining timeframes: {remaining}")

    # Phase 2 — remaining timeframes
    for tf in remaining:
        try:
            print(f"[screener_job] Warming {tf}...")
            await precompute_all_coins(timeframe=tf)
            print(f"[screener_job] ✅ {tf} ready")
        except Exception as e:
            print(f"[screener_job] ❌ Error warming {tf}: {e}")

    print("[screener_job] ✅ Startup warmup fully complete — all timeframes ready")


def setup_screener_jobs(application: Application):
    """
    Sets up screener background jobs and triggers immediate startup warmup.

    Call this in your main bot initialization AFTER application.initialize().

    What happens:
    - Immediately fires a background task to warm priority caches (1h, 4h, 1d)
    - Schedules hourly refresh job to keep all caches fresh
    - Users get live results ~15 minutes after deploy (not 30+ minutes)

    Args:
        application: The Telegram Application instance
    """
    job_queue = application.job_queue

    # ----------------------------------------------------------------
    # 1. Fire startup warmup immediately as a background task.
    #    This does NOT block the bot from starting or accepting commands.
    # ----------------------------------------------------------------
    async def _trigger_startup(context):
        # Wrap in create_task so the job returns immediately
        # and warmup runs fully in the background
        asyncio.create_task(_startup_warmup())

    job_queue.run_once(_trigger_startup, when=10)  # 10 seconds after bot starts
    print("[screener_job] Startup warmup scheduled in 10 seconds")

    # ----------------------------------------------------------------
    # 2. Schedule hourly refresh job.
    #    first=JOB_INTERVAL means it runs 1 hour after startup,
    #    by which point the startup warmup is already done.
    # ----------------------------------------------------------------
    job_queue.run_repeating(
        run_screener_precompute_job,
        interval=JOB_INTERVAL,
        first=JOB_INTERVAL  # First scheduled refresh after 1 hour
    )
    print(f"[screener_job] Hourly refresh scheduled every {JOB_INTERVAL}s")
    print(f"[screener_job] Priority timeframes: {PRIORITY_TIMEFRAMES}")
    print(f"[screener_job] All timeframes: {ALL_TIMEFRAMES}")


# ----------------------------------------------------------------
# Manual / admin utilities (unchanged API, improved internals)
# ----------------------------------------------------------------

async def force_precompute_now(timeframe: str = None, parallel: bool = False):
    """
    Manually trigger pre-computation (useful for testing or admin commands).

    Args:
        timeframe: Specific timeframe to pre-compute. If None, pre-computes all.
        parallel: If True and timeframe is None, runs all timeframes in parallel.
                  WARNING: parallel mode may hit API rate limits.
    """
    if timeframe:
        print(f"[screener_job] Manual pre-computation triggered for {timeframe}...")
        await precompute_all_coins(timeframe=timeframe)
        print(f"[screener_job] Completed {timeframe}")

    elif parallel:
        print("[screener_job] Manual parallel pre-computation for all timeframes...")
        tasks = [precompute_all_coins(timeframe=tf) for tf in ALL_TIMEFRAMES]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for tf, result in zip(ALL_TIMEFRAMES, results):
            if isinstance(result, Exception):
                print(f"[screener_job] ❌ {tf} failed: {result}")
            else:
                print(f"[screener_job] ✅ {tf} complete")

    else:
        print("[screener_job] Manual sequential pre-computation for all timeframes...")
        for tf in ALL_TIMEFRAMES:
            print(f"[screener_job] Pre-computing {tf}...")
            try:
                await precompute_all_coins(timeframe=tf)
                print(f"[screener_job] ✅ {tf} complete")
            except Exception as e:
                print(f"[screener_job] ❌ {tf} failed: {e}")


async def force_precompute_priority_timeframes():
    """
    Pre-compute only priority timeframes (1h, 4h, 1d).
    Useful for quick cache re-warming without waiting for all timeframes.
    """
    print(f"[screener_job] Pre-computing priority timeframes: {PRIORITY_TIMEFRAMES}")

    for tf in PRIORITY_TIMEFRAMES:
        try:
            await precompute_all_coins(timeframe=tf)
            print(f"[screener_job] ✅ {tf} complete")
        except Exception as e:
            print(f"[screener_job] ❌ {tf} failed: {e}")

    print("[screener_job] Priority timeframes pre-computation complete")
