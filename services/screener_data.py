# services/screener_data.py
import aiohttp
import os
import asyncio
import time
from dotenv import load_dotenv
from typing import Optional, Dict, Any, List
from collections import deque

load_dotenv()
COINMARKETCAP_API = os.getenv("COINMARKETCAP_API_KEY")
TWELVE_DATA_API = os.getenv("TWELVE_DATA_API_KEY")  # Still used for technical indicators

CMC_BASE_URL = "https://pro-api.coinmarketcap.com/v1"
TWELVE_BASE_URL = "https://api.twelvedata.com"
REQUEST_TIMEOUT = 10  # seconds
MAX_RETRIES = 2
CACHE_TTL = 600 # 5 minutes in seconds

# Rate limiting: 20 requests per minute for CMC
RATE_LIMIT_WINDOW = 60  # seconds
MAX_REQUESTS_PER_WINDOW = 20
_request_times: deque = deque(maxlen=MAX_REQUESTS_PER_WINDOW)
_rate_limit_lock = asyncio.Lock()

# In-memory cache: {cache_key: (data, timestamp)}
_cache: Dict[str, tuple[Any, float]] = {}


# ------------------------------
# Rate Limiting
# ------------------------------
async def _wait_for_rate_limit():
    """Enforce rate limit of 20 requests per minute."""
    async with _rate_limit_lock:
        now = time.time()
        
        # Remove timestamps outside the window
        while _request_times and now - _request_times[0] > RATE_LIMIT_WINDOW:
            _request_times.popleft()
        
        # If we've hit the limit, wait
        if len(_request_times) >= MAX_REQUESTS_PER_WINDOW:
            wait_time = RATE_LIMIT_WINDOW - (now - _request_times[0]) + 0.1
            if wait_time > 0:
                await asyncio.sleep(wait_time)
                # Clear old timestamps after waiting
                now = time.time()
                while _request_times and now - _request_times[0] > RATE_LIMIT_WINDOW:
                    _request_times.popleft()
        
        # Record this request
        _request_times.append(time.time())


# ------------------------------
# Cache Management
# ------------------------------
def _get_cache_key(symbol: str, interval: str, endpoint: str, params: str = "") -> str:
    """Generate unique cache key for API request."""
    return f"{endpoint}:{symbol}:{interval}:{params}"


def _get_from_cache(key: str) -> Optional[Any]:
    """Retrieve data from cache if not expired."""
    if key in _cache:
        data, timestamp = _cache[key]
        if time.time() - timestamp < CACHE_TTL:
            return data
        else:
            # Cache expired, remove it
            del _cache[key]
    return None


def _set_cache(key: str, data: Any) -> None:
    """Store data in cache with current timestamp."""
    _cache[key] = (data, time.time())


def clear_cache() -> None:
    """Clear all cached data (useful for testing or manual refresh)."""
    _cache.clear()


# ------------------------------
# Generic JSON Fetcher with Retry Logic and Caching
# ------------------------------
async def fetch_json(url: str, headers: Optional[Dict] = None, cache_key: Optional[str] = None, 
                     use_rate_limit: bool = False, retries: int = MAX_RETRIES) -> Optional[Dict[str, Any]]:
    """
    Fetches JSON with timeout, retry logic, and caching.
    Returns None if all attempts fail.
    """
    # Check cache first
    if cache_key:
        cached_data = _get_from_cache(cache_key)
        if cached_data is not None:
            return cached_data
    
    # Apply rate limiting if needed
    if use_rate_limit:
        await _wait_for_rate_limit()
    
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    
    for attempt in range(retries + 1):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as r:
                    if r.status == 200:
                        data = await r.json()
                        # Validate response has expected structure
                        if data and isinstance(data, dict):
                            # Check for API error messages (both CMC and TwelveData formats)
                            if "status" in data and data["status"] == "error":
                                return None
                            if "status" in data and isinstance(data["status"], dict):
                                if data["status"].get("error_code") != 0:
                                    return None
                            # Cache successful response
                            if cache_key:
                                _set_cache(cache_key, data)
                            return data
                    elif r.status == 429:  # Rate limit
                        if attempt < retries:
                            await asyncio.sleep(2 * (attempt + 1))  # Longer backoff
                            continue
                    return None
        except asyncio.TimeoutError:
            if attempt < retries:
                await asyncio.sleep(0.5)
                continue
            return None
        except (aiohttp.ClientError, Exception):
            if attempt < retries:
                await asyncio.sleep(0.5)
                continue
            return None
    
    return None


# ------------------------------
# CoinMarketCap OHLCV Fetcher
# ------------------------------
async def get_cmc_ohlcv(symbol: str, interval: str = "hourly", count: int = 60) -> Optional[List[Dict[str, Any]]]:
    """
    Fetches OHLCV data from CoinMarketCap.
    interval: 'hourly', 'daily', '5m', '15m', '30m', '1h', '4h', etc.
    Returns list of candles sorted newest → oldest.
    """
    if not COINMARKETCAP_API:
        return None
    
    symbol = symbol.strip().upper().replace("/USD", "")
    
    # Map interval to CMC format
    interval_map = {
        "5m": "5m", "15m": "15m", "30m": "30m",
        "1h": "hourly", "4h": "4h", "1d": "daily", "1day": "daily"
    }
    cmc_interval = interval_map.get(interval, "hourly")
    
    cache_key = _get_cache_key(symbol, cmc_interval, "cmc_ohlcv", f"count={count}")
    
    headers = {
        "X-CMC_PRO_API_KEY": COINMARKETCAP_API,
        "Accept": "application/json"
    }
    
    url = f"{CMC_BASE_URL}/cryptocurrency/ohlcv/historical?symbol={symbol}&time_period={cmc_interval}&count={count}&convert=USD"
    
    data = await fetch_json(url, headers=headers, cache_key=cache_key, use_rate_limit=True)
    
    if not data or "data" not in data:
        return None
    
    quotes = data["data"].get("quotes", [])
    if not isinstance(quotes, list) or len(quotes) == 0:
        return None
    
    # Convert CMC format to standard format
    candles = []
    for q in quotes:
        quote = q.get("quote", {}).get("USD", {})
        candles.append({
            "datetime": q.get("time_open"),
            "open": quote.get("open"),
            "high": quote.get("high"),
            "low": quote.get("low"),
            "close": quote.get("close"),
            "volume": quote.get("volume")
        })
    
    # Reverse to get newest first
    candles.reverse()
    
    return candles


# ------------------------------
# Calculate Technical Indicators from OHLCV
# ------------------------------
def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """Calculate RSI from price list."""
    if len(prices) < period + 1:
        return None
    
    gains = []
    losses = []
    
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    
    if len(gains) < period:
        return None
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    # Calculate subsequent values
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def calculate_ema(prices: List[float], period: int) -> Optional[float]:
    """Calculate EMA from price list."""
    if len(prices) < period:
        return None
    
    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period  # Start with SMA
    
    for price in prices[period:]:
        ema = (price * multiplier) + (ema * (1 - multiplier))
    
    return ema


def calculate_macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Optional[Dict[str, float]]:
    """Calculate MACD from price list."""
    if len(prices) < slow + signal:
        return None
    
    # Calculate EMAs
    ema_fast = calculate_ema(prices[-fast:], fast)
    ema_slow = calculate_ema(prices[-slow:], slow)
    
    if ema_fast is None or ema_slow is None:
        return None
    
    macd_line = ema_fast - ema_slow
    
    # For signal line, we need to calculate EMA of MACD values
    # Simplified: use the current MACD as approximation
    # For full accuracy, would need historical MACD values
    
    return {
        "macd": macd_line,
        "signal": macd_line * 0.9,  # Approximation
        "hist": macd_line * 0.1
    }


# ------------------------------
# TwelveData Fallback for Indicators
# ------------------------------
async def get_twelve_indicator(symbol: str, interval: str, indicator: str, params: str = "") -> Optional[Dict[str, Any]]:
    """
    Fetches indicator data from TwelveData (fallback for complex indicators).
    """
    if not TWELVE_DATA_API:
        return None
    
    symbol = symbol.strip().upper()
    cache_key = _get_cache_key(symbol, interval, f"twelve_{indicator}", params)
    
    url = f"{TWELVE_BASE_URL}/{indicator}?symbol={symbol}&interval={interval}&apikey={TWELVE_DATA_API}{params}"
    return await fetch_json(url, cache_key=cache_key)


# ------------------------------
# Safe Float Conversion
# ------------------------------
def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """Safely converts value to float, returns default on failure."""
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


# ------------------------------
# Bullish Engulfing Detector
# ------------------------------
def is_bullish_engulfing(c1: Dict[str, float], c2: Dict[str, float]) -> bool:
    """
    c1 = previous candle, c2 = current candle
    Returns False if data is invalid.
    """
    try:
        if not all(k in c1 and k in c2 for k in ["open", "close"]):
            return False
        
        c1_open = safe_float(c1["open"])
        c1_close = safe_float(c1["close"])
        c2_open = safe_float(c2["open"])
        c2_close = safe_float(c2["close"])
        
        if None in [c1_open, c1_close, c2_open, c2_close]:
            return False
        
        # Candle 1 must be bearish
        if c1_close >= c1_open:
            return False
        
        # Candle 2 must be bullish
        if c2_close <= c2_open:
            return False
        
        # Candle 2 must engulf candle 1
        return (c2_open <= c1_close) and (c2_close >= c1_open)
    
    except (KeyError, TypeError):
        return False


# ------------------------------
# Load All Screener Data
# ------------------------------
async def load_screener_data(symbol: str, interval: str = "1h") -> Dict[str, Any]:
    """
    Loads all screener data using CoinMarketCap as primary source.
    Falls back to TwelveData only for complex indicators if needed.
    Results are cached for 5 minutes.
    """
    complete_cache_key = f"screener_complete:{symbol}:{interval}"
    cached_result = _get_from_cache(complete_cache_key)
    if cached_result is not None:
        return cached_result
    
    data = {
        "close": None,
        "prev_close": None,
        "rsi": None,
        "macd": None,
        "signal": None,
        "hist": None,
        "ema20": None,
        "ema50": None,
        "ema200": None,
        "volume": None,
        "volume_ma": None,
        "candle_1": None,
        "candle_2": None,
        "avg_7d": None,
        "support": None,
        "resistance": None,
        "bullish_engulfing": False,
    }

    # Fetch OHLCV data from CoinMarketCap
    candles = await get_cmc_ohlcv(symbol, interval, 200)
    daily_candles = await get_cmc_ohlcv(symbol, "daily", 10)
    
    if not candles or len(candles) < 2:
        _set_cache(complete_cache_key, data)
        return data
    
    # Extract price and volume data
    try:
        data["close"] = safe_float(candles[0].get("close"))
        data["prev_close"] = safe_float(candles[1].get("close"))
        data["volume"] = safe_float(candles[0].get("volume"))
        
        # Volume MA 20
        if len(candles) >= 20:
            vols = [safe_float(c.get("volume"), 0) for c in candles[:20]]
            vols = [v for v in vols if v is not None and v > 0]
            if vols:
                data["volume_ma"] = sum(vols) / len(vols)
        
        # Candles for pattern detection
        data["candle_1"] = {
            "open": safe_float(candles[1].get("open")),
            "close": safe_float(candles[1].get("close"))
        }
        data["candle_2"] = {
            "open": safe_float(candles[0].get("open")),
            "close": safe_float(candles[0].get("close"))
        }
        
        # Detect bullish engulfing
        if all(data["candle_1"].get(k) is not None for k in ["open", "close"]):
            if all(data["candle_2"].get(k) is not None for k in ["open", "close"]):
                data["bullish_engulfing"] = is_bullish_engulfing(data["candle_1"], data["candle_2"])
    except (KeyError, IndexError, TypeError):
        pass
    
    # Calculate indicators from OHLCV
    closes = [safe_float(c.get("close")) for c in reversed(candles)]
    closes = [c for c in closes if c is not None]
    
    if len(closes) >= 200:
        data["rsi"] = calculate_rsi(closes[-100:], 14)
        data["ema20"] = calculate_ema(closes[-50:], 20)
        data["ema50"] = calculate_ema(closes[-100:], 50)
        data["ema200"] = calculate_ema(closes, 200)
        
        macd_result = calculate_macd(closes[-50:])
        if macd_result:
            data["macd"] = macd_result["macd"]
            data["signal"] = macd_result["signal"]
            data["hist"] = macd_result["hist"]
    
    # Process daily candles for 7-day average and support/resistance
    if daily_candles and len(daily_candles) >= 7:
        try:
            closes_7d = [safe_float(c.get("close")) for c in daily_candles[:7]]
            closes_7d = [c for c in closes_7d if c is not None]
            
            if len(closes_7d) == 7:
                data["avg_7d"] = sum(closes_7d) / 7
            
            if len(daily_candles) >= 5:
                highs = [safe_float(c.get("high")) for c in daily_candles[:5]]
                lows = [safe_float(c.get("low")) for c in daily_candles[:5]]
                
                highs = [h for h in highs if h is not None]
                lows = [l for l in lows if l is not None]
                
                if highs:
                    data["resistance"] = max(highs)
                if lows:
                    data["support"] = min(lows)
        except (KeyError, TypeError):
            pass
    
    # Cache the complete result
    _set_cache(complete_cache_key, data)
    
    return data