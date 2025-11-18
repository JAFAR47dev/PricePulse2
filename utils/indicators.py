import os
import asyncio
import httpx
import math
import time
from dotenv import load_dotenv

# 🔑 Load API key
load_dotenv()
TWELVE_API_KEY = os.getenv("TWELVE_DATA_API_KEY")
BASE_URL = "https://api.twelvedata.com/time_series"

# ----------------------------- In-Memory Cache -----------------------------
_cache = {}
CACHE_TTL = 60  # seconds to keep data fresh

def get_cache_key(symbol, interval):
    return f"{symbol.upper()}_{interval}"

def get_cached_data(symbol, interval):
    key = get_cache_key(symbol, interval)
    entry = _cache.get(key)
    if entry and (time.time() - entry["timestamp"] < CACHE_TTL):
        return entry["data"]
    return None

def set_cache(symbol, interval, data):
    _cache[get_cache_key(symbol, interval)] = {
        "data": data,
        "timestamp": time.time()
    }

# ----------------------------- Helper Functions -----------------------------

def calculate_ema(prices, period):
    if len(prices) < period:
        return prices[-1]
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for price in prices[period:]:
        ema = price * k + ema * (1 - k)
    return ema

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    gains, losses = 0, 0
    for i in range(1, period + 1):
        diff = prices[i] - prices[i - 1]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    avg_gain = gains / period
    avg_loss = losses / period
    for i in range(period + 1, len(prices)):
        diff = prices[i] - prices[i - 1]
        gain = max(diff, 0)
        loss = abs(min(diff, 0))
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_macd(prices, fast=12, slow=26, signal=9):
    if len(prices) < slow + signal:
        return 0, 0, 0
    ema_fast = calculate_ema(prices, fast)
    ema_slow = calculate_ema(prices, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema([macd_line for _ in range(signal)], signal)
    macd_hist = macd_line - signal_line
    return macd_line, signal_line, macd_hist

# ----------------------------- Main Function -----------------------------

async def get_crypto_indicators(symbol: str = "BTC/USD", interval: str = "1h", outputsize: int = 100):
    """
    Fetch OHLCV from Twelve Data and calculate RSI, EMA20, MACD,
    and 24h high/low/volume. Cached for 60 seconds per (symbol+interval).
    """
    symbol = symbol.upper().replace("USDT", "USD")

    # 🧠 Check cache first
    cached = get_cached_data(symbol, interval)
    if cached:
        print(f"⚡ Using cached data for {symbol} [{interval}]")
        return cached

    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": TWELVE_API_KEY,
        "format": "JSON",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        for attempt in range(3):
            resp = await client.get(BASE_URL, params=params)
            if resp.status_code == 200:
                break
            elif resp.status_code == 429:
                await asyncio.sleep(2 * (attempt + 1))
            else:
                print(f"❌ Twelve Data API error {resp.status_code}")
                return None

        data = resp.json()

    if "values" not in data or not data["values"]:
        print(f"⚠️ No data found for {symbol}")
        return None

    candles = list(reversed(data["values"]))
    closes = [float(c["close"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    volumes = [float(c.get("volume", 0) or 0) for c in candles]

    ema20 = calculate_ema(closes, 20)
    rsi_val = calculate_rsi(closes)
    macd_val, macd_signal, macd_hist = calculate_macd(closes)

    if interval.endswith("h"):
        window = 24
    elif interval.endswith("m"):
        try:
            window = int(24 * 60 / int(interval[:-1]))
        except:
            window = 24
    else:
        window = 1

    last_window = candles[-window:]
    high_24h = max(float(c["high"]) for c in last_window)
    low_24h = min(float(c["low"]) for c in last_window)
    volume_24h = sum(float(c.get("volume", 0) or 0) for c in last_window)

    latest = candles[-1]
    latest_close = float(latest["close"])
    latest_volume = float(latest.get("volume", 0) or 0)

    result = {
        "symbol": symbol,
        "interval": interval,
        "price": round(latest_close, 4),
        "rsi": round(rsi_val, 2),
        "ema20": round(ema20, 2),
        "macd": round(macd_val, 2),
        "macdSignal": round(macd_signal, 2),
        "macdHist": round(macd_hist, 2),
        "volume": round(latest_volume, 2),
        "high_24h": round(high_24h, 4),
        "low_24h": round(low_24h, 4),
        "volume_24h": round(volume_24h, 2),
    }

    # 💾 Cache it for future use
    set_cache(symbol, interval, result)
    print(f"✅ Cached {symbol} [{interval}] for {CACHE_TTL}s")

    return result


#import os
#import asyncio
#import httpx
#import pandas as pd
#import ta
#from dotenv import load_dotenv

# Load API key
#load_dotenv()
#TWELVE_API_KEY = os.getenv("TWELVE_DATA_API_KEY")

#BASE_URL = "https://api.twelvedata.com/time_series"


#async def get_crypto_indicators(symbol: str = "BTC/USD", interval: str = "1h", outputsize: int = 100):
#    """
#    Fetches OHLCV data from Twelve Data and calculates RSI, EMA20, MACD,
#    plus 24h high, low, and volume.
#    Supports forex, crypto, and stocks.
#    """

#    params = {
#        "symbol": symbol.upper(),
#        "interval": interval,
#        "outputsize": outputsize,
#        "apikey": TWELVE_API_KEY,
#        "format": "JSON",
#    }

#    async with httpx.AsyncClient(timeout=15.0) as client:
#        resp = await client.get(BASE_URL, params=params)

#        if resp.status_code != 200:
#            print(f"❌ Failed to fetch Twelve Data API ({resp.status_code})")
#            print(await resp.text())
#            return None

#        data = resp.json()

#    if "values" not in data or not data["values"]:
#        print(f"⚠️ No data found for {symbol}")
#        return None

#    # 📊 Convert to DataFrame
#    df = pd.DataFrame(data["values"])
#    df = df.astype({
#        "open": float,
#        "high": float,
#        "low": float,
#        "close": float,
#        "volume": float
#    })
#    df["datetime"] = pd.to_datetime(df["datetime"])
#    df = df.sort_values("datetime")  # oldest → newest

#    # 🧮 Compute indicators
#    df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
#    df["ema20"] = ta.trend.EMAIndicator(df["close"], window=20).ema_indicator()

#    macd = ta.trend.MACD(df["close"])
#    df["macd"] = macd.macd()
#    df["macd_signal"] = macd.macd_signal()
#    df["macd_hist"] = macd.macd_diff()

#    # 🎯 Latest values
#    latest = df.iloc[-1]

#    # 🕒 Compute 24h high/low/volume (approx last 24 candles if 1h interval)
#    if interval.endswith("h"):
#        window = 24
#    elif interval.endswith("m"):
#        window = int(24 * 60 / int(interval[:-1]))  # e.g., 15m → 96 points
#    else:
#        window = 1

#    last_window = df.tail(window)
#    high_24h = last_window["high"].max()
#    low_24h = last_window["low"].min()
#    volume_24h = last_window["volume"].sum()

#    # ✅ Final result
#    result = {
#        "symbol": symbol.upper(),
#        "price": round(latest["close"], 4),
#        "rsi": round(latest["rsi"], 2),
#        "ema20": round(latest["ema20"], 2),
#        "macd": round(latest["macd"], 2),
#        "macdSignal": round(latest["macd_signal"], 2),
#        "macdHist": round(latest["macd_hist"], 2),
#        "volume": round(latest["volume"], 2),
#        "high_24h": round(high_24h, 4),
#        "low_24h": round(low_24h, 4),
#        "volume_24h": round(volume_24h, 2),
#        "interval": interval,
#    }

#    return result



import os
import aiohttp
from dotenv import load_dotenv
from time import time

# Load environment variables
load_dotenv()
CRYPTOCOMPARE_API_KEY = os.getenv("CRYPTOCOMPARE_API_KEY")
CRYPTOCOMPARE_BASE_URL = "https://min-api.cryptocompare.com"

# 🧠 Cache memory (symbol_timeframe → {timestamp, data})
_volume_cache = {}
CACHE_TTL = 120  # seconds (2 minutes cache lifespan)

async def get_volume_comparison(symbol: str, timeframe: str):
    """
    Returns current and average volume for a given symbol and timeframe using live CryptoCompare data.
    Caches results for short periods (default: 2 minutes) to avoid redundant API calls.
    """

    key = f"{symbol.lower()}_{timeframe}"
    now = time.time()

    # ✅ Return cached data if still fresh
    if key in _volume_cache and now - _volume_cache[key]["timestamp"] < CACHE_TTL:
        return _volume_cache[key]["data"]

    # ✅ Supported timeframes (mapped to CryptoCompare intervals)
    tf_map = {
        "15m": {"endpoint": "histominute", "limit": 96},  # last 24h (15-min intervals)
        "30m": {"endpoint": "histominute", "limit": 48},  # last 24h (30-min intervals)
        "1h": {"endpoint": "histohour", "limit": 24},     # last 24h
        "4h": {"endpoint": "histohour", "limit": 42},     # last 7d
        "1d": {"endpoint": "histoday", "limit": 30},      # last 30d
        "7d": {"endpoint": "histoday", "limit": 90},      # last 90d
        "14d": {"endpoint": "histoday", "limit": 180},
        "30d": {"endpoint": "histoday", "limit": 365},
        "90d": {"endpoint": "histoday", "limit": 730},
        "180d": {"endpoint": "histoday", "limit": 1095},
        "365d": {"endpoint": "histoday", "limit": 2000},
    }

    if timeframe not in tf_map:
        raise ValueError(f"❌ Invalid timeframe: {timeframe}")

    tf_info = tf_map[timeframe]
    endpoint = tf_info["endpoint"]
    limit = tf_info["limit"]

    # 🌐 Build API URL
    url = f"{CRYPTOCOMPARE_BASE_URL}/data/v2/{endpoint}"
    params = {
        "fsym": symbol.upper(),
        "tsym": "USD",
        "limit": limit,
        "api_key": CRYPTOCOMPARE_API_KEY
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"⚠️ CryptoCompare request failed (HTTP {resp.status}): {text}")
            data = await resp.json()

    # 🧮 Extract and validate data
    if "Data" not in data or "Data" not in data["Data"]:
        raise Exception(f"⚠️ Unexpected API response for {symbol}: {data}")

    candles = data["Data"]["Data"]
    volumes = [candle.get("volumeto", 0) for candle in candles if candle.get("volumeto")]

    if not volumes:
        raise Exception(f"⚠️ No volume data found for {symbol}")

    current_volume = volumes[-1]
    average_volume = sum(volumes[:-1]) / max(1, len(volumes) - 1)
    result = (round(current_volume, 2), round(average_volume, 2))

    # 🧠 Store result in cache
    _volume_cache[key] = {"timestamp": now, "data": result}

    return result
      
import aiohttp
import os
import time

from dotenv import load_dotenv
load_dotenv()

TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY")

# Cache dictionary: _cache[symbol][indicator_name] = {"value": ..., "timestamp": ...}
_indicator_cache = {}
CACHE_TTL = 120  # seconds


def is_fresh(entry):
    return time.time() - entry["timestamp"] < CACHE_TTL


# === GET RSI ===
async def get_cached_rsi(symbol):
    symbol = symbol.upper()
    if symbol in _indicator_cache and "rsi" in _indicator_cache[symbol]:
        if is_fresh(_indicator_cache[symbol]["rsi"]):
            return _indicator_cache[symbol]["rsi"]["value"]

    url = (
        f"https://api.twelvedata.com/rsi?symbol={symbol}/USDT&interval=1h"
        f"&apikey={TWELVE_DATA_API_KEY}&time_period=14"
    )

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            value = float(data.get("values", [{}])[0].get("rsi", 0))

            if symbol not in _indicator_cache:
                _indicator_cache[symbol] = {}
            _indicator_cache[symbol]["rsi"] = {"value": value, "timestamp": time.time()}
            return value


# === GET MACD ===
async def get_cached_macd(symbol):
    symbol = symbol.upper()
    if symbol in _indicator_cache and "macd" in _indicator_cache[symbol]:
        if is_fresh(_indicator_cache[symbol]["macd"]):
            return _indicator_cache[symbol]["macd"]["value"]

    url = (
        f"https://api.twelvedata.com/macd?symbol={symbol}/USDT&interval=1h"
        f"&apikey={TWELVE_DATA_API_KEY}&short_period=12&long_period=26&signal_period=9"
    )

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            val = data.get("values", [{}])[0]
            macd = float(val.get("macd", 0))
            signal = float(val.get("macd_signal", 0))
            hist = float(val.get("macd_histogram", 0))

            if symbol not in _indicator_cache:
                _indicator_cache[symbol] = {}
            _indicator_cache[symbol]["macd"] = {
                "value": (macd, signal, hist),
                "timestamp": time.time()
            }
            return macd, signal, hist


# === GET EMA ===
async def get_cached_ema(symbol, period=20):
    symbol = symbol.upper()
    key = f"ema{period}"

    if symbol in _indicator_cache and key in _indicator_cache[symbol]:
        if is_fresh(_indicator_cache[symbol][key]):
            return _indicator_cache[symbol][key]["value"]

    url = (
        f"https://api.twelvedata.com/ema?symbol={symbol}/USDT&interval=1h"
        f"&time_period={period}&apikey={TWELVE_DATA_API_KEY}"
    )

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            ema = float(data.get("values", [{}])[0].get("ema", 0))

            if symbol not in _indicator_cache:
                _indicator_cache[symbol] = {}
            _indicator_cache[symbol][key] = {
                "value": ema,
                "timestamp": time.time()
            }
            return ema