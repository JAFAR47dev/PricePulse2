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

# ----------------------------- Indicator Helpers -----------------------------

def calculate_ema(prices, period):
    if len(prices) == 0:
        return None

    # If fewer prices exist, return the average of what's available
    if len(prices) < period:
        return sum(prices) / len(prices)

    k = 2 / (period + 1)

    # Start with SMA as seed
    ema = sum(prices[:period]) / period

    # Apply EMA formula on remaining prices
    for price in prices[period:]:
        ema = (price - ema) * k + ema

    return ema
    

def calculate_rsi(prices, period=14):
    length = len(prices)

    # Not enough data → neutral RSI
    if length < period + 1:
        return 50.0

    # Step 1: Initial average gain/loss
    gains, losses = 0.0, 0.0
    for i in range(1, period + 1):
        diff = prices[i] - prices[i - 1]
        if diff > 0:
            gains += diff
        else:
            losses += abs(diff)

    avg_gain = gains / period
    avg_loss = losses / period

    # Step 2: Wilder smoothing
    for i in range(period + 1, length):
        diff = prices[i] - prices[i - 1]
        gain = max(diff, 0)
        loss = abs(min(diff, 0))

        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    # Step 3: Calculate RSI
    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi
    
def calculate_macd(prices, fast=12, slow=26, signal=9):
    if len(prices) < slow + signal:
        return 0, 0, 0

    # --- Step 1: Fast EMA series ---
    ema_fast_series = []
    k_fast = 2 / (fast + 1)
    ema = sum(prices[:fast]) / fast
    ema_fast_series.append(ema)
    for price in prices[fast:]:
        ema = price * k_fast + ema * (1 - k_fast)
        ema_fast_series.append(ema)

    # --- Step 2: Slow EMA series ---
    ema_slow_series = []
    k_slow = 2 / (slow + 1)
    ema = sum(prices[:slow]) / slow
    ema_slow_series.append(ema)
    for price in prices[slow:]:
        ema = price * k_slow + ema * (1 - k_slow)
        ema_slow_series.append(ema)

    # Align fast and slow EMA series by truncating start
    offset = slow - fast
    ema_fast_series = ema_fast_series[offset:]

    # --- Step 3: MACD Series ---
    macd_series = [
        fast_ema - slow_ema
        for fast_ema, slow_ema in zip(ema_fast_series, ema_slow_series)
    ]

    # --- Step 4: Signal Line (EMA of MACD series) ---
    if len(macd_series) < signal:
        return 0, 0, 0

    k_signal = 2 / (signal + 1)
    ema = sum(macd_series[:signal]) / signal
    for value in macd_series[signal:]:
        ema = value * k_signal + ema * (1 - k_signal)
    signal_line = ema

    macd_line = macd_series[-1]
    macd_hist = macd_line - signal_line

    return macd_line, signal_line, macd_hist
    
def calculate_stochastic(highs, lows, closes, period=14, d_period=3):
    if len(closes) < period + d_period:
        return 50, 50

    # %K calculation
    highest = max(highs[-period:])
    lowest = min(lows[-period:])

    if highest == lowest:
        k = 50
    else:
        k = (closes[-1] - lowest) / (highest - lowest) * 100

    # --- REAL %D using last %K values ---
    # Build last d_period K values properly
    k_values = []
    for i in range(d_period):
        h = max(highs[-period-i : len(highs)-i])
        l = min(lows[-period-i : len(lows)-i])
        if h == l:
            k_values.append(50)
        else:
            k_values.append((closes[-1-i] - l) / (h - l) * 100)

    d = sum(k_values) / d_period  # SMA

    return k, d
    

def calculate_cci(highs, lows, closes, period=20):
    if len(closes) < period:
        return 0
    tp = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(len(closes))]
    sma = sum(tp[-period:]) / period
    md = sum(abs(tp[i] - sma) for i in range(len(tp) - period, len(tp))) / period
    if md == 0:
        return 0
    return (tp[-1] - sma) / (0.015 * md)

def calculate_atr(highs, lows, closes, period=14):
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )
        trs.append(tr)

    # If not enough data, return average TR so far (more accurate)
    if len(trs) < period:
        return sum(trs) / len(trs)

    # Standard ATR = SMA of last N TRs
    return sum(trs[-period:]) / period

def calculate_mfi(highs, lows, closes, volumes, period=14):
    if len(closes) < period + 1:
        return 50  # neutral fallback

    typical_prices = [
        (highs[i] + lows[i] + closes[i]) / 3
        for i in range(len(closes))
    ]

    pos_flow = 0
    neg_flow = 0

    start = len(closes) - period

    for i in range(start, len(closes)):
        money_flow = typical_prices[i] * volumes[i]

        if typical_prices[i] > typical_prices[i - 1]:
            pos_flow += money_flow
        elif typical_prices[i] < typical_prices[i - 1]:
            neg_flow += money_flow
        # If equal, ignore (no flow)

    if neg_flow == 0:
        return 100

    ratio = pos_flow / neg_flow
    return 100 - (100 / (1 + ratio))
    
def calculate_adx(highs, lows, closes, period=14):
    """
    Calculate ADX (Average Directional Index) and +DI / -DI
    Returns: adx, plus_di, minus_di
    """
    if len(highs) < period + 1:
        return 0.0, 0.0, 0.0  # Not enough data

    tr_list = []
    plus_dm = []
    minus_dm = []

    for i in range(1, len(highs)):
        high_diff = highs[i] - highs[i - 1]
        low_diff = lows[i - 1] - lows[i]

        # True Range
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )
        tr_list.append(tr)

        # Directional movements
        plus_dm.append(high_diff if high_diff > low_diff and high_diff > 0 else 0)
        minus_dm.append(low_diff if low_diff > high_diff and low_diff > 0 else 0)

    # Smooth TR, +DM, -DM using Wilder's smoothing
    def smooth(series, period):
        smoothed = []
        smoothed.append(sum(series[:period]))
        for i in range(period, len(series)):
            value = smoothed[-1] - (smoothed[-1] / period) + series[i]
            smoothed.append(value)
        return smoothed

    tr_smooth = smooth(tr_list, period)
    plus_dm_smooth = smooth(plus_dm, period)
    minus_dm_smooth = smooth(minus_dm, period)

    plus_di = [(100 * (p / t)) for p, t in zip(plus_dm_smooth, tr_smooth)]
    minus_di = [(100 * (m / t)) for m, t in zip(minus_dm_smooth, tr_smooth)]

    dx = [(abs(p - m) / (p + m) * 100) if (p + m) != 0 else 0 for p, m in zip(plus_di, minus_di)]

    # ADX = smoothed DX
    if len(dx) < period:
        adx = sum(dx) / len(dx)
    else:
        adx = sum(dx[:period]) / period
        for i in range(period, len(dx)):
            adx = ((adx * (period - 1)) + dx[i]) / period

    return round(adx, 2), round(plus_di[-1], 2), round(minus_di[-1], 2)
    
    
def calculate_vwap(closes, volumes):
    """
    Calculate VWAP (Volume Weighted Average Price)
    Returns a single float value for the VWAP over the provided data.
    """
    if not closes or not volumes or len(closes) != len(volumes):
        return None  # invalid input

    cumulative_vol_price = 0.0
    cumulative_volume = 0.0

    for price, volume in zip(closes, volumes):
        cumulative_vol_price += price * volume
        cumulative_volume += volume

    if cumulative_volume == 0:
        return None  # avoid division by zero

    vwap = cumulative_vol_price / cumulative_volume
    return round(vwap, 4)
    
def calculate_bbands(closes, period=20):
    if len(closes) < period:
        return None, None, None

    window = closes[-period:]
    sma = sum(window) / period

    # Sample standard deviation (period - 1)
    variance = sum((c - sma) ** 2 for c in window) / (period - 1)
    std = variance ** 0.5

    upper = sma + 2 * std
    lower = sma - 2 * std

    return upper, sma, lower
    
# ----------------------------- Main Function -----------------------------

async def get_crypto_indicators(symbol: str = "BTC/USD", interval: str = "1h", outputsize: int = 100):
    symbol = symbol.upper().replace("USDT", "USD")

    # Cache check
    cached = get_cached_data(symbol, interval)
    if cached:
        return cached

    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": TWELVE_API_KEY,
        "format": "JSON",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(BASE_URL, params=params)

    data = resp.json()
    if "values" not in data or not data["values"]:
        return None

    candles = list(reversed(data["values"]))
    closes = [float(c["close"]) for c in candles]
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    volumes = [float(c.get("volume", 0) or 0) for c in candles]

    # ---- Existing calculations ----
    ema20 = calculate_ema(closes, 20)
    rsi_val = calculate_rsi(closes)
    macd_val, macd_signal, macd_hist = calculate_macd(closes)

    # ---- NEW indicators ----
    stoch_k, stoch_d = calculate_stochastic(highs, lows, closes)
    cci_val = calculate_cci(highs, lows, closes)
    atr_val = calculate_atr(highs, lows, closes)
    mfi_val = calculate_mfi(highs, lows, closes, volumes)
    bb_upper, bb_mid, bb_lower = calculate_bbands(closes)
    adx_val = calculate_adx(highs, lows, closes, period=14) 
    vwap_val = calculate_vwap(closes, volumes)             

    latest = candles[-1]
    last_price = float(latest["close"])

    # Safe rounding helper
    def safe_round(val, digits=2):
        return round(val, digits) if isinstance(val, (int, float)) else None

    # Build result safely
    result = {
        "symbol": symbol,
        "interval": interval,
        "price": safe_round(last_price, 4),
        "ema20": safe_round(ema20, 2),
        "rsi": safe_round(rsi_val, 2),
        "macd": safe_round(macd_val, 2),
        "macdSignal": safe_round(macd_signal, 2),
        "macdHist": safe_round(macd_hist, 2),
        "stochK": safe_round(stoch_k, 2),
        "stochD": safe_round(stoch_d, 2),
        "cci": safe_round(cci_val, 2),
        "atr": safe_round(atr_val, 4),
        "mfi": safe_round(mfi_val, 2),
        "bbUpper": safe_round(bb_upper, 2),
        "bbMiddle": safe_round(bb_mid, 2),
        "bbLower": safe_round(bb_lower, 2),
        "adx": safe_round(adx_val, 2),
        "vwap": safe_round(vwap_val, 2),
    }


    set_cache(symbol, interval, result)
    return result
    


import os
import asyncio
import aiohttp
from dotenv import load_dotenv
from time import time  # ✅ Import the time function directly
from typing import Tuple, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
CRYPTOCOMPARE_API_KEY = os.getenv("CRYPTOCOMPARE_API_KEY")
CRYPTOCOMPARE_BASE_URL = "https://min-api.cryptocompare.com"

# Validate API key at startup
if not CRYPTOCOMPARE_API_KEY:
    logger.warning("⚠️ CRYPTOCOMPARE_API_KEY not found in environment variables")

# 🧠 Cache memory (symbol_timeframe → {timestamp, data})
_volume_cache = {}
CACHE_TTL = 120  # seconds (2 minutes cache lifespan)

# Request configuration
REQUEST_TIMEOUT = 30  # seconds
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds


async def get_volume_comparison(
    symbol: str, 
    timeframe: str,
    use_cache: bool = True
) -> Tuple[float, float]:
    """
    Returns current and average volume for a given symbol and timeframe using live CryptoCompare data.
    Caches results for short periods (default: 2 minutes) to avoid redundant API calls.
    
    Args:
        symbol: Trading pair symbol (e.g., 'BTC', 'ETH')
        timeframe: Time interval for analysis (e.g., '1h', '1d')
        use_cache: Whether to use cached data if available
        
    Returns:
        Tuple of (current_volume, average_volume)
        
    Raises:
        ValueError: If timeframe is invalid or symbol is empty
        Exception: If API request fails or returns invalid data
    """
    
    # Input validation
    if not symbol or not isinstance(symbol, str):
        raise ValueError("❌ Symbol must be a non-empty string")
    
    if not timeframe or not isinstance(timeframe, str):
        raise ValueError("❌ Timeframe must be a non-empty string")
    
    symbol = symbol.strip().upper()
    timeframe = timeframe.strip().lower()
    
    if not symbol:
        raise ValueError("❌ Symbol cannot be empty after stripping whitespace")

    key = f"{symbol.lower()}_{timeframe}"
    now = time.time()

    # ✅ Return cached data if still fresh and caching is enabled
    if use_cache and key in _volume_cache:
        cache_entry = _volume_cache[key]
        if now - cache_entry["timestamp"] < CACHE_TTL:
            logger.debug(f"📦 Returning cached data for {key}")
            return cache_entry["data"]

    # ✅ Supported timeframes (mapped to CryptoCompare intervals)
    tf_map = {
        "1m": {"endpoint": "histominute", "limit": 1440, "aggregate": 1},   # last 24h (1-min intervals)
        "5m": {"endpoint": "histominute", "limit": 288, "aggregate": 5},    # last 24h (5-min intervals)
        "15m": {"endpoint": "histominute", "limit": 96, "aggregate": 15},   # last 24h (15-min intervals)
        "30m": {"endpoint": "histominute", "limit": 48, "aggregate": 30},   # last 24h (30-min intervals)
        "1h": {"endpoint": "histohour", "limit": 25, "aggregate": 1},       # last 25h (to get 24 complete + 1 current)
        "4h": {"endpoint": "histohour", "limit": 43, "aggregate": 4},       # last 7d + current
        "1d": {"endpoint": "histoday", "limit": 31, "aggregate": 1},        # last 30d + current
        "7d": {"endpoint": "histoday", "limit": 91, "aggregate": 7},        # last 90d + current
        "14d": {"endpoint": "histoday", "limit": 181, "aggregate": 14},     # last ~6 months + current
        "30d": {"endpoint": "histoday", "limit": 366, "aggregate": 30},     # last ~3 years + current
        "90d": {"endpoint": "histoday", "limit": 731, "aggregate": 90},     # last ~6 years + current
        "180d": {"endpoint": "histoday", "limit": 1096, "aggregate": 180},  # last ~9 years + current
        "365d": {"endpoint": "histoday", "limit": 2001, "aggregate": 365},  # maximum history + current
    }

    if timeframe not in tf_map:
        valid_timeframes = ", ".join(tf_map.keys())
        raise ValueError(
            f"❌ Invalid timeframe: '{timeframe}'. "
            f"Valid options: {valid_timeframes}"
        )

    tf_info = tf_map[timeframe]
    endpoint = tf_info["endpoint"]
    limit = tf_info["limit"]
    aggregate = tf_info.get("aggregate", 1)

    # 🌐 Build API URL
    url = f"{CRYPTOCOMPARE_BASE_URL}/data/v2/{endpoint}"
    params = {
        "fsym": symbol,
        "tsym": "USD",
        "limit": limit,
        "aggregate": aggregate
    }
    
    # Only add API key if it exists
    if CRYPTOCOMPARE_API_KEY:
        params["api_key"] = CRYPTOCOMPARE_API_KEY
    else:
        logger.warning("⚠️ Making request without API key - rate limits may apply")

    # Retry logic with exponential backoff
    last_exception = None
    data = None
    
    for attempt in range(MAX_RETRIES):
        try:
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params) as resp:
                    # Handle different HTTP status codes
                    if resp.status == 200:
                        data = await resp.json()
                        break
                    elif resp.status == 429:
                        # Rate limit hit
                        retry_after = int(resp.headers.get('Retry-After', RETRY_DELAY * (2 ** attempt)))
                        logger.warning(f"⚠️ Rate limited. Retrying after {retry_after}s...")
                        await asyncio.sleep(retry_after)
                        continue
                    elif resp.status in (401, 403):
                        text = await resp.text()
                        raise Exception(f"❌ Authentication failed (HTTP {resp.status}): {text}")
                    elif resp.status == 404:
                        raise ValueError(f"❌ Symbol '{symbol}' not found")
                    else:
                        text = await resp.text()
                        raise Exception(f"⚠️ CryptoCompare request failed (HTTP {resp.status}): {text}")
                        
        except asyncio.TimeoutError as e:
            last_exception = e
            logger.warning(f"⚠️ Request timeout (attempt {attempt + 1}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (2 ** attempt))
                continue
            raise Exception(f"❌ Request timed out after {MAX_RETRIES} attempts")
            
        except aiohttp.ClientError as e:
            last_exception = e
            logger.warning(f"⚠️ Network error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (2 ** attempt))
                continue
            raise Exception(f"❌ Network error after {MAX_RETRIES} attempts: {e}")
    
    # Check if we got data after all retries
    if data is None:
        if last_exception:
            raise Exception(f"❌ Failed after {MAX_RETRIES} attempts: {last_exception}")
        raise Exception(f"❌ Failed to fetch data after {MAX_RETRIES} attempts")

    # 🧮 Extract and validate data
    if not isinstance(data, dict):
        raise Exception(f"⚠️ Invalid API response type: expected dict, got {type(data)}")
    
    if "Data" not in data:
        error_msg = data.get("Message", "Unknown error")
        raise Exception(f"⚠️ API error for {symbol}: {error_msg}")
    
    if not isinstance(data["Data"], dict) or "Data" not in data["Data"]:
        raise Exception(f"⚠️ Unexpected API response structure for {symbol}")

    candles = data["Data"]["Data"]
    
    if not isinstance(candles, list):
        raise Exception(f"⚠️ Expected list of candles, got {type(candles)}")
    
    if len(candles) < 3:  # Need at least 3: current + 2 historical for average
        raise Exception(f"⚠️ Insufficient data for {symbol}: only {len(candles)} candle(s) available")

    # Extract volumes with better validation
    volumes = []
    timestamps = []
    for i, candle in enumerate(candles):
        if not isinstance(candle, dict):
            logger.warning(f"⚠️ Skipping invalid candle at index {i}")
            continue
        
        volume = candle.get("volumeto")
        timestamp = candle.get("time")
        if volume is not None and isinstance(volume, (int, float)) and volume >= 0:
            volumes.append(float(volume))
            if timestamp:
                timestamps.append(timestamp)

    if not volumes:
        raise Exception(f"⚠️ No valid volume data found for {symbol}")
    
    if len(volumes) < 3:
        raise Exception(f"⚠️ Insufficient volume data for {symbol}: only {len(volumes)} value(s)")

    # 🔍 DEBUG: Log the last few volumes to understand the pattern
    logger.info(f"📊 Last 5 volumes for {symbol} ({timeframe}): {[f'{v:,.0f}' for v in volumes[-5:]]}")
    
    # 🔥 Use the LAST candle as current (it's the most recent complete or forming candle)
    # Use all PREVIOUS candles for the average
    current_volume = volumes[-1]  
    historical_volumes = volumes[:-1]  
    
    if not historical_volumes:
        raise Exception(f"⚠️ Not enough historical data for {symbol}")
    
    average_volume = sum(historical_volumes) / len(historical_volumes)
    
    # 🔍 Additional debug info
    logger.info(f"📊 {symbol} ({timeframe}) - Current: ${current_volume:,.2f}, Avg: ${average_volume:,.2f}, Min: ${min(historical_volumes):,.2f}, Max: ${max(historical_volumes):,.2f}")
    
    result = (round(current_volume, 2), round(average_volume, 2))

    # 🧠 Store result in cache
    _volume_cache[key] = {"timestamp": now, "data": result}
    logger.info(f"✅ Volume comparison for {symbol} ({timeframe}): current={current_volume:,.2f}, avg={average_volume:,.2f}")

    return result
       
def clear_cache(symbol: Optional[str] = None, timeframe: Optional[str] = None):
    """
    Clear cache entries. If symbol and timeframe are provided, clears specific entry.
    Otherwise, clears entire cache.
    
    Args:
        symbol: Optional symbol to clear
        timeframe: Optional timeframe to clear
    """
    global _volume_cache
    
    if symbol and timeframe:
        key = f"{symbol.lower()}_{timeframe.lower()}"
        if key in _volume_cache:
            del _volume_cache[key]
            logger.info(f"🧹 Cleared cache for {key}")
    else:
        _volume_cache.clear()
        logger.info("🧹 Cleared entire cache")


def get_cache_stats() -> dict:
    """
    Returns statistics about the current cache state.
    
    Returns:
        Dictionary with cache statistics
    """
    now = time.time()  # ✅ Call time() function correctly
    active_entries = sum(
        1 for entry in _volume_cache.values()
        if now - entry["timestamp"] < CACHE_TTL
    )
    
    return {
        "total_entries": len(_volume_cache),
        "active_entries": active_entries,
        "stale_entries": len(_volume_cache) - active_entries,
        "cache_ttl": CACHE_TTL
    }

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