# notifications/services/notification_data.py
import asyncio
import time

# Import your refactored reusable functions
from handlers.best_gainers import get_top_gainers_message
from handlers.worst_losers import get_top_losers_message
from handlers.global_data import get_global_market_message
from handlers.news import get_latest_crypto_news
from handlers.gasfees import get_gas_fees
from handlers.daily_coin import get_coin_of_the_day

# --- Caching Layer ---
_cache = {"data": None, "expires": 0}

async def get_notification_data(ttl=300):
    """
    Fetch and cache all notification data.
    Returns dict with all sections: global, gainers, losers, news, gas, cod.
    Cache expires after 'ttl' seconds (default 5 minutes).
    """
    now = time.time()
    if _cache["data"] and now < _cache["expires"]:
        return _cache["data"]

    try:
        # Fetch all notifications concurrently
        (
            global_market,
            gainers,
            losers,
            news,
            gas,
            cod
        ) = await asyncio.gather(
            _safe_call(get_global_market_message),
            _safe_call(get_top_gainers_message),
            _safe_call(get_top_losers_message),
            _safe_call(get_latest_crypto_news),
            _safe_call(get_gas_fees),
            _safe_call(get_coin_of_the_day)
        )

        data = {
            "global": global_market or "🌍 Global data unavailable",
            "gainers": gainers or "📈 Gainers data unavailable",
            "losers": losers or "📉 Losers data unavailable",
            "news": news or "📰 News unavailable",
            "gas": gas or "⛽ Gas data unavailable",
            "cod": cod or "🪙 Coin of the Day unavailable"
        }

        _cache["data"] = data
        _cache["expires"] = now + ttl  # refresh every 5 minutes by default
        return data

    except Exception as e:
        print(f"[NotificationData] Error fetching data: {e}")
        return _cache["data"] or {}

async def _safe_call(func):
    """
    Runs a possibly sync or async function safely.
    Ensures one failed API doesn’t crash all notifications.
    """
    try:
        if asyncio.iscoroutinefunction(func):
            return await func()
        else:
            return func()
    except Exception as e:
        print(f"[NotificationData] Error in {func.__name__}: {e}")
        return None