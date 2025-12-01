# fav/utils/fav_prices_async.py
import os
import time
import aiohttp
from dotenv import load_dotenv

load_dotenv()

CMC_API_KEY = os.getenv("CMC_API_KEY")
CMC_QUOTES_URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
CMC_HISTORICAL_URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/historical"
COINGECKO_MARKETS = "https://api.coingecko.com/api/v3/coins/markets"

# -------------------------------------------------
# SIMPLE IN-MEMORY CACHE (60 seconds lifespan)
# -------------------------------------------------
CACHE = {}
CACHE_TTL = 60   # seconds


def cache_get(key):
    if key in CACHE:
        value, timestamp = CACHE[key]
        if time.time() - timestamp < CACHE_TTL:
            return value
    return None


def cache_set(key, value):
    CACHE[key] = (value, time.time())


# -----------------------------
# RSI Calculator (unchanged)
# -----------------------------
def calculate_rsi(closes):
    if len(closes) < 15:
        return None

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d for d in deltas if d > 0]
    losses = [-d for d in deltas if d < 0]

    avg_gain = (sum(gains) / 14) if gains else 0
    avg_loss = (sum(losses) / 14) if losses else 0

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss if avg_loss != 0 else float("inf")
    return round(100 - (100 / (1 + rs)), 2)


# -----------------------------------
# Async Market Data Fetcher
# -----------------------------------
async def fetch_market_data(symbols: list):
    """
    Returns: { "BTC": {price, percent, trend, rank}, ... }
    Always returns dict (maybe empty).
    """
    if not symbols:
        return {}

    cache_key = f"market_{','.join(symbols)}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    # -------------------------
    # FIRST: Try CMC
    # -------------------------
    if CMC_API_KEY:
        try:
            headers = {"X-CMC_PRO_API_KEY": CMC_API_KEY}
            params = {"symbol": ",".join(symbols), "convert": "USD"}

            async with aiohttp.ClientSession() as session:
                async with session.get(CMC_QUOTES_URL, headers=headers, params=params, timeout=10) as r:
                    data = await r.json()

            data_block = data.get("data", {})
            results = {}

            for sym in symbols:
                entry = data_block.get(sym)
                if not entry:
                    continue

                if isinstance(entry, list) and len(entry) > 0:
                    d = entry[0]
                elif isinstance(entry, dict):
                    d = entry
                else:
                    continue

                try:
                    quote = d.get("quote", {}).get("USD", {})
                    price = float(quote.get("price")) if quote.get("price") else None
                    percent = float(quote.get("percent_change_24h")) if quote.get("percent_change_24h") else None
                    rank = d.get("cmc_rank", "?")

                    if percent is not None:
                        if percent > 0.5:
                            trend = "📈 Bullish"
                        elif percent < -0.5:
                            trend = "📉 Bearish"
                        else:
                            trend = "➖ Neutral"
                    else:
                        trend = "➖ Neutral"

                    results[sym] = {
                        "price": round(price, 2) if price else None,
                        "percent": round(percent, 2) if percent else None,
                        "trend": trend,
                        "rank": rank,
                    }
                except:
                    continue

            if results:
                cache_set(cache_key, results)
                return results

        except Exception as e:
            print(f"[fav_prices] CMC fetch failed: {e}")

    # -------------------------
    # SECOND: CoinGecko fallback
    # -------------------------
    try:
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 250,
            "page": 1,
            "sparkline": "false",
            "price_change_percentage": "24h",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(COINGECKO_MARKETS, params=params, timeout=12) as r:
                data = await r.json()

        cg_map = {d["symbol"].upper(): d for d in data if "symbol" in d}

        results = {}

        for sym in symbols:
            d = cg_map.get(sym)
            if not d:
                continue

            price = d.get("current_price")
            percent = d.get("price_change_percentage_24h")
            rank = d.get("market_cap_rank", "?")

            if percent is not None:
                if percent > 0.5:
                    trend = "📈 Bullish"
                elif percent < -0.5:
                    trend = "📉 Bearish"
                else:
                    trend = "➖ Neutral"
            else:
                trend = "➖ Neutral"

            results[sym] = {
                "price": round(price, 2) if price else None,
                "percent": round(percent, 2) if percent else None,
                "trend": trend,
                "rank": rank,
            }

        cache_set(cache_key, results)
        return results

    except Exception as e:
        print(f"[fav_prices] CoinGecko fallback failed: {e}")

    cache_set(cache_key, {})
    return {}

import aiohttp
import os
import time
from dotenv import load_dotenv

load_dotenv()

TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY")

CACHE_TTL = 120  # seconds
_indicator_cache = {}  # { cache_key: { "value": x, "timestamp": t } }


def cache_get(key):
    entry = _indicator_cache.get(key)
    if entry and (time.time() - entry["timestamp"] < CACHE_TTL):
        return entry["value"]
    return None


def cache_set(key, value):
    _indicator_cache[key] = {
        "value": value,
        "timestamp": time.time(),
    }


# -----------------------------
# Async RSI Fetcher (single)
# -----------------------------
async def fetch_rsi(symbol: str):
    symbol = symbol.upper()
    cache_key = f"rsi_{symbol}"

    # Cache check
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    url = (
        "https://api.twelvedata.com/rsi?"
        f"symbol={symbol}USDT&interval=1h&time_period=14&apikey={TWELVE_DATA_API_KEY}"
    )

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=12) as resp:
                data = await resp.json()

        # API error
        if "status" in data and data["status"] == "error":
            cache_set(cache_key, None)
            return None

        values = data.get("values", [])
        if not values:
            cache_set(cache_key, None)
            return None

        rsi_value = float(values[0].get("rsi", 0))

        cache_set(cache_key, rsi_value)
        return rsi_value

    except Exception:
        cache_set(cache_key, None)
        return None
        

# ---------------------------------
# SINGLE COIN FETCH
# ---------------------------------
async def get_fav_price(symbol: str):
    data = await get_fav_prices([symbol])
    return data.get(symbol)


import asyncio

# ---------------------------------
# MULTI-COIN FETCH (Optimized)
# ---------------------------------
async def get_fav_prices(symbols: list):
    symbols = [s.upper() for s in symbols]

    # Fetch market data in one batch (your existing function)
    market = await fetch_market_data(symbols)

    # --- Fetch all RSI values in parallel ---
    rsi_tasks = {sym: asyncio.create_task(fetch_rsi(sym)) for sym in symbols}
    rsi_results = {sym: await task for sym, task in rsi_tasks.items()}

    final = {}

    for sym in symbols:
        entry = market.get(sym)
        if not entry:
            continue

        entry["rsi"] = rsi_results.get(sym)
        final[sym] = entry

    return final