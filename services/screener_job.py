# services/screener_job.py
import asyncio
from telegram import Bot
from telegram.ext import Application
from services.screener_engine import precompute_all_coins, is_cache_fresh
from notifications.scheduler import run_signal_check

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

            # FIX: context.bot is valid here — this is a PTB job callback
            await run_signal_check(context.bot)
            print(f"[screener_job] Completed {timeframe}")

        except Exception as e:
            print(f"[screener_job] Error during pre-computation for {timeframe}: {e}")
            continue

    print("[screener_job] All timeframe pre-computations completed")


async def _startup_warmup(bot: Bot):
    """
    Runs immediately at bot startup (as a background task).

    FIX: Accepts bot as an explicit parameter instead of referencing
    context.bot — _startup_warmup is not a PTB job callback so it
    has no context. The bot is passed in from _trigger_startup below.

    Phase 1: Warm up priority timeframes (1h, 4h, 1d) first — ~15 minutes.
    Phase 2: Warm up remaining timeframes (5m, 15m, 30m) in the background.
    """
    print("[screener_job] 🚀 Startup warmup started...")
    print(f"[screener_job] Phase 1: Warming priority timeframes: {PRIORITY_TIMEFRAMES}")

    # Phase 1 — priority timeframes first
    for tf in PRIORITY_TIMEFRAMES:
        try:
            print(f"[screener_job] Warming {tf}...")
            await precompute_all_coins(timeframe=tf)

            # FIX: use bot directly, not context.bot
            await run_signal_check(bot)
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

            # FIX: use bot directly, not context.bot
            await run_signal_check(bot)
            print(f"[screener_job] ✅ {tf} ready")
        except Exception as e:
            print(f"[screener_job] ❌ Error warming {tf}: {e}")

    print("[screener_job] ✅ Startup warmup fully complete — all timeframes ready")


def setup_screener_jobs(application: Application):
    """
    Sets up screener background jobs and triggers immediate startup warmup.
    """
    job_queue = application.job_queue

    async def _trigger_startup(context):
        # FIX: pass context.bot explicitly into _startup_warmup
        # so it can call run_signal_check(bot) without having context itself
        asyncio.create_task(_startup_warmup(context.bot))

    job_queue.run_once(_trigger_startup, when=100)
    print("[screener_job] Startup warmup scheduled in 10 seconds")

    job_queue.run_repeating(
        run_screener_precompute_job,
        interval=JOB_INTERVAL,
        first=JOB_INTERVAL
    )
    print(f"[screener_job] Hourly refresh scheduled every {JOB_INTERVAL}s")
    print(f"[screener_job] Priority timeframes: {PRIORITY_TIMEFRAMES}")
    print(f"[screener_job] All timeframes: {ALL_TIMEFRAMES}")


# ----------------------------------------------------------------
# Manual / admin utilities
# ----------------------------------------------------------------

async def force_precompute_now(timeframe: str = None, parallel: bool = False):
    """
    Manually trigger pre-computation (useful for testing or admin commands).
    Note: does NOT fire signal checks — manual runs are for cache warming only.
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
