# fav/utils/fav_prices.py

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

CMC_API_KEY = os.getenv("CMC_API_KEY")
CMC_QUOTES_URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
CMC_HISTORICAL_URL = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/historical"

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
# RSI Calculator
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

    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


# -----------------------------------
# Fetch Current Market Data (Price, %)
# -----------------------------------
def fetch_market_data(symbols: list):
    cache_key = f"market_{','.join(symbols)}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    symbols_str = ",".join(symbols)
    headers = {"X-CMC_PRO_API_KEY": CMC_API_KEY}

    params = {
        "symbol": symbols_str,
        "convert": "USD"
    }

    r = requests.get(CMC_QUOTES_URL, headers=headers, params=params)
    data = r.json()

    results = {}
    for sym in symbols:
        try:
            d = data["data"][sym][0]
            quote = d["quote"]["USD"]

            price = round(quote["price"], 2)
            percent = round(quote["percent_change_24h"], 2)
            rank = d.get("cmc_rank", "?")

            # Determine trend
            if percent > 0.5:
                trend = "📈 Bullish"
            elif percent < -0.5:
                trend = "📉 Bearish"
            else:
                trend = "➖ Neutral"

            results[sym] = {
                "price": price,
                "percent": percent,
                "trend": trend,
                "rank": rank
            }

        except Exception:
            continue

    cache_set(cache_key, results)
    return results


# -----------------------------
# Fetch RSI
# -----------------------------
def fetch_rsi(symbol: str):
    cache_key = f"rsi_{symbol}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    headers = {"X-CMC_PRO_API_KEY": CMC_API_KEY}

    params = {
        "symbol": symbol,
        "convert": "USD",
        "interval": "1h",
        "count": 30
    }

    try:
        r = requests.get(CMC_HISTORICAL_URL, headers=headers, params=params)
        data = r.json()

        closes = [p["quote"]["USD"]["close"] for p in data["data"]["quotes"]]
        rsi = calculate_rsi(closes)

    except Exception:
        rsi = None

    cache_set(cache_key, rsi)
    return rsi


# -----------------------------
# Main function (single coin)
# -----------------------------
def get_fav_price(symbol: str):
    data = get_fav_prices([symbol])
    return data.get(symbol)


# -----------------------------
# Multi-coin fetch function
# -----------------------------
def get_fav_prices(symbols: list):
    market = fetch_market_data(symbols)
    final = {}

    for sym in symbols:
        if sym not in market:
            continue

        rsi = fetch_rsi(sym)
        market[sym]["rsi"] = rsi
        final[sym] = market[sym]

    return final