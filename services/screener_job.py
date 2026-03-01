# services/screener_job.py
import asyncio
from telegram.ext import Application
from services.screener_engine import precompute_all_coins, is_cache_fresh

# Job runs every 1 hour
JOB_INTERVAL = 3600 # 1 hour in seconds

# Timeframes to pre-compute
PRECOMPUTE_TIMEFRAMES = ["5m", "15m", "30m", "1h", "4h", "1d"]


async def run_screener_precompute_job(context):
    """
    Background job that pre-fetches data for all 100 coins across multiple timeframes.
    Runs every 1 hour to keep cache fresh.
    
    Note: This will take ~30 minutes to complete all timeframes sequentially
    (5 minutes per timeframe × 6 timeframes). Consider running timeframes
    in parallel if you need faster updates.
    """
    print("[screener_job] Starting scheduled pre-computation for all timeframes...")
    
    for timeframe in PRECOMPUTE_TIMEFRAMES:
        try:
            # Check if cache is still fresh for this timeframe
            if is_cache_fresh(timeframe, max_age_seconds=JOB_INTERVAL):
                print(f"[screener_job] Cache still fresh for {timeframe}, skipping...")
                continue
            
            print(f"[screener_job] Pre-computing {timeframe} timeframe...")
            await precompute_all_coins(timeframe=timeframe)
            print(f"[screener_job] Completed {timeframe} timeframe")
            
        except Exception as e:
            print(f"[screener_job] Error during pre-computation for {timeframe}: {e}")
            # Continue with next timeframe even if one fails
            continue
    
    print("[screener_job] All timeframe pre-computations completed")


async def run_screener_precompute_job_parallel(context):
    """
    Alternative: Pre-compute all timeframes in parallel for faster completion.
    Takes ~5 minutes total but uses more resources and API calls.
    
    WARNING: This may hit API rate limits if you're on a restricted plan.
    Use the sequential version (run_screener_precompute_job) for safer operation.
    """
    print("[screener_job] Starting parallel pre-computation for all timeframes...")
    
    tasks = []
    for timeframe in PRECOMPUTE_TIMEFRAMES:
        # Skip if cache is fresh
        if is_cache_fresh(timeframe, max_age_seconds=JOB_INTERVAL):
            print(f"[screener_job] Cache still fresh for {timeframe}, skipping...")
            continue
        
        tasks.append(precompute_all_coins(timeframe=timeframe))
    
    if tasks:
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
            print("[screener_job] Parallel pre-computation completed")
        except Exception as e:
            print(f"[screener_job] Error during parallel pre-computation: {e}")
    else:
        print("[screener_job] All caches are fresh, no pre-computation needed")


def setup_screener_jobs(application: Application, use_parallel: bool = False):
    """
    Set up the background job for screener pre-computation.
    Call this in your main bot initialization.
    
    Args:
        application: The Telegram Application instance
        use_parallel: If True, pre-compute timeframes in parallel (faster but more resource-intensive)
                     If False, pre-compute sequentially (slower but safer)
    """
    job_queue = application.job_queue
    
    # Choose which job to run
    job_callback = run_screener_precompute_job_parallel if use_parallel else run_screener_precompute_job
    job_type = "parallel" if use_parallel else "sequential"
    
    # Run every 10 minutes, starting 20 minutes after bot starts
    # (giving bot time to fully initialize)
    job_queue.run_repeating(
        job_callback,
        interval=JOB_INTERVAL,
        first=1800  # Start first run after 1800 seconds (30 minutes)
    )
    
    print(f"[screener_job] Scheduled {job_type} pre-computation every {JOB_INTERVAL}s (10 minutes)")
    print(f"[screener_job] First run in 30 minutes")
    print(f"[screener_job] Timeframes to pre-compute: {', '.join(PRECOMPUTE_TIMEFRAMES)}")


async def force_precompute_now(timeframe: str = None, parallel: bool = False):
    """
    Manually trigger pre-computation (useful for testing or admin commands).
    
    Args:
        timeframe: Specific timeframe to pre-compute (e.g., "1h"). 
                  If None, pre-computes all timeframes.
        parallel: If True and timeframe is None, pre-compute all timeframes in parallel
    """
    if timeframe:
        print(f"[screener_job] Manual pre-computation triggered for {timeframe}...")
        await precompute_all_coins(timeframe=timeframe)
        print(f"[screener_job] Completed pre-computation for {timeframe}")
    elif parallel:
        print("[screener_job] Manual parallel pre-computation triggered for all timeframes...")
        tasks = [precompute_all_coins(timeframe=tf) for tf in PRECOMPUTE_TIMEFRAMES]
        await asyncio.gather(*tasks, return_exceptions=True)
        print("[screener_job] Completed parallel pre-computation for all timeframes")
    else:
        print("[screener_job] Manual sequential pre-computation triggered for all timeframes...")
        for tf in PRECOMPUTE_TIMEFRAMES:
            print(f"[screener_job] Pre-computing {tf}...")
            await precompute_all_coins(timeframe=tf)
        print("[screener_job] Completed sequential pre-computation for all timeframes")


async def force_precompute_priority_timeframes():
    """
    Pre-compute only the most commonly used timeframes (1h, 4h, 1d).
    Useful for quick cache warming without waiting for all timeframes.
    """
    priority_timeframes = ["1h", "4h", "1d"]
    print(f"[screener_job] Pre-computing priority timeframes: {', '.join(priority_timeframes)}")
    
    for tf in priority_timeframes:
        try:
            await precompute_all_coins(timeframe=tf)
            print(f"[screener_job] Completed {tf}")
        except Exception as e:
            print(f"[screener_job] Error pre-computing {tf}: {e}")
    
    print("[screener_job] Priority timeframes pre-computation completed")