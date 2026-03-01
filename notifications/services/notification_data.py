# notifications/services/notification_data.py
import asyncio
import time

# Import DATA functions (not message functions)
from handlers.best_gainers import get_top_gainers_data
from handlers.worst_losers import get_top_losers_data
from handlers.global_data import get_global_market_data
from handlers.news import get_latest_crypto_news_data
from handlers.gasfees import get_gas_fees_data
from handlers.daily_coin import get_coin_of_the_day_data

_cache = {"data": None, "expires": 0}

async def get_notification_data(ttl=300):
    """
    Fetch and cache all notification data as RAW DATA.
    Returns dict with all sections.
    """
    now = time.time()
    if _cache["data"] and now < _cache["expires"]:
        return _cache["data"]

    try:
        (
            global_market,
            gainers,
            losers,
            news,
            gas,
            cod
        ) = await asyncio.gather(
            _safe_call(get_global_market_data),
            _safe_call(get_top_gainers_data),
            _safe_call(get_top_losers_data),
            _safe_call(get_latest_crypto_news_data),
            _safe_call(get_gas_fees_data),
            _safe_call(get_coin_of_the_day_data)
        )

        data = {
            "global": global_market or {},
            "gainers": gainers or [],
            "losers": losers or [],
            "news": news or [],
            "gas": gas or {},
            "cod": cod or {}
        }

        _cache["data"] = data
        _cache["expires"] = now + ttl
        return data

    except Exception as e:
        print(f"[NotificationData] Error fetching data: {e}")
        return _cache["data"] or {}

async def _safe_call(func):
    try:
        if asyncio.iscoroutinefunction(func):
            return await func()
        else:
            return func()
    except Exception as e:
        print(f"[NotificationData] Error in {func.__name__}: {e}")
        return None