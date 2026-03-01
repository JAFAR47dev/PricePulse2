# services/screener_data.py - BULLETPROOF VERSION with DNS fallbacks
import aiohttp
import os
import asyncio
import time
from datetime import datetime
from dotenv import load_dotenv
from typing import Optional, Dict, Any, List
from collections import deque

load_dotenv()

# Multiple API endpoints as fallbacks
BINANCE_ENDPOINTS = [
    "https://api.binance.com/api/v3",
    "https://api1.binance.com/api/v3",
    "https://api2.binance.com/api/v3",
    "https://api3.binance.com/api/v3",
    "https://data-api.binance.vision/api/v3",  # Binance data mirror
]

REQUEST_TIMEOUT = 10
MAX_RETRIES = 2
CACHE_TTL = 300  # 5 minutes

# Rate limiting
RATE_LIMIT_WINDOW = 60
MAX_REQUESTS_PER_WINDOW = 500
_request_times: deque = deque(maxlen=MAX_REQUESTS_PER_WINDOW)
_rate_limit_lock = asyncio.Lock()
_cache: Dict[str, tuple[Any, float]] = {}
_working_endpoint = None  # Cache the working endpoint


async def _wait_for_rate_limit():
    """Enforce rate limit."""
    async with _rate_limit_lock:
        now = time.time()
        
        while _request_times and now - _request_times[0] > RATE_LIMIT_WINDOW:
            _request_times.popleft()
        
        if len(_request_times) >= MAX_REQUESTS_PER_WINDOW:
            wait_time = RATE_LIMIT_WINDOW - (now - _request_times[0]) + 0.1
            if wait_time > 0:
                await asyncio.sleep(wait_time)
                now = time.time()
                while _request_times and now - _request_times[0] > RATE_LIMIT_WINDOW:
                    _request_times.popleft()
        
        _request_times.append(time.time())


def _get_cache_key(symbol: str, interval: str, endpoint: str, params: str = "") -> str:
    """Generate unique cache key."""
    return f"{endpoint}:{symbol}:{interval}:{params}"


def _get_from_cache(key: str) -> Optional[Any]:
    """Retrieve from cache if not expired."""
    if key in _cache:
        data, timestamp = _cache[key]
        if time.time() - timestamp < CACHE_TTL:
            return data
        del _cache[key]
    return None


def _set_cache(key: str, data: Any) -> None:
    """Store in cache."""
    _cache[key] = (data, time.time())


def clear_cache() -> None:
    """Clear all cached data."""
    global _working_endpoint
    _cache.clear()
    _working_endpoint = None


def normalize_symbol_for_binance(symbol: str) -> str:
    """Convert various symbol formats to Binance format."""
    symbol = symbol.strip().upper()
    symbol = symbol.replace("/", "")
    
    if symbol.endswith("USDT"):
        return symbol
    
    if symbol.endswith("USD"):
        return symbol[:-3] + "USDT"
    
    return symbol + "USDT"


def binance_interval_map(interval: str) -> str:
    """Map common interval names to Binance format."""
    interval_mapping = {
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d",
        "1day": "1d",
        "daily": "1d",
        "hourly": "1h",
    }
    
    return interval_mapping.get(interval, interval)


async def fetch_with_fallback(path: str, params: Dict = None) -> Optional[List]:
    """
    Fetch from Binance with automatic endpoint fallback.
    Tries multiple endpoints if DNS fails.
    """
    global _working_endpoint
    
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT, connect=5)
    
    # Try cached working endpoint first
    endpoints_to_try = []
    if _working_endpoint:
        endpoints_to_try.append(_working_endpoint)
    
    # Add all other endpoints
    for endpoint in BINANCE_ENDPOINTS:
        if endpoint not in endpoints_to_try:
            endpoints_to_try.append(endpoint)
    
    last_error = None
    
    for endpoint in endpoints_to_try:
        url = f"{endpoint}/{path}"
        
        try:
            # Use connector with custom DNS resolver settings
            connector = aiohttp.TCPConnector(
                force_close=True,
                enable_cleanup_closed=True,
                ttl_dns_cache=300
            )
            
            async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        # Cache this working endpoint
                        if _working_endpoint != endpoint:
                            _working_endpoint = endpoint
                            print(f"[screener] ✅ Using Binance endpoint: {endpoint}")
                        
                        return data
                    
                    elif resp.status == 429:
                        await asyncio.sleep(1)
                        continue
                    
                    else:
                        error_text = await resp.text()
                        last_error = f"HTTP {resp.status}: {error_text}"
                        continue
        
        except asyncio.TimeoutError:
            last_error = f"Timeout for {endpoint}"
            continue
        
        except Exception as e:
            last_error = str(e)
            # Try next endpoint
            continue
    
    # All endpoints failed
    print(f"[screener] ❌ All Binance endpoints failed. Last error: {last_error}")
    return None


async def get_binance_ohlcv(symbol: str, interval: str = "1h", limit: int = 200) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch OHLCV data from Binance with DNS fallback.
    
    Args:
        symbol: Trading symbol (e.g., "BTC/USDT", "ETH")
        interval: Timeframe - "5m", "15m", "30m", "1h", "4h", "1d"
        limit: Number of candles (max 1000)
    
    Returns:
        List of candles (newest → oldest) or None
    """
    binance_symbol = normalize_symbol_for_binance(symbol)
    binance_interval = binance_interval_map(interval)
    limit = min(limit, 1000)
    
    cache_key = _get_cache_key(binance_symbol, binance_interval, "binance_klines", f"limit={limit}")
    
    # Check cache
    cached = _get_from_cache(cache_key)
    if cached:
        return cached
    
    await _wait_for_rate_limit()
    
    params = {
        "symbol": binance_symbol,
        "interval": binance_interval,
        "limit": limit
    }
    
    data = await fetch_with_fallback("klines", params)
    
    if not data or not isinstance(data, list):
        return None
    
    # Convert Binance format to our format
    candles = []
    for k in data:
        candles.append({
            "datetime": datetime.fromtimestamp(k[0] / 1000).isoformat(),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5])
        })
    
    # Reverse to get newest first
    candles.reverse()
    
    # Cache and return
    _set_cache(cache_key, candles)
    
    return candles


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """Safely convert to float."""
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """Calculate RSI."""
    if not prices or len(prices) < period + 1:
        return None
    
    gains, losses = [], []
    
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
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return round(rsi, 2)


def calculate_ema(prices: List[float], period: int) -> Optional[float]:
    """Calculate EMA."""
    if not prices or len(prices) < period:
        return None
    
    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    
    return round(ema, 4)


def calculate_macd(prices: List[float], fast: int = 12, slow: int = 26, signal_period: int = 9) -> Optional[Dict[str, float]]:
    """Calculate MACD."""
    if not prices or len(prices) < slow + signal_period:
        return None
    
    macd_series = []
    
    for i in range(slow, len(prices) + 1):
        price_window = prices[:i]
        fast_ema = calculate_ema(price_window, fast)
        slow_ema = calculate_ema(price_window, slow)
        
        if fast_ema is not None and slow_ema is not None:
            macd_series.append(fast_ema - slow_ema)
    
    if len(macd_series) < signal_period:
        return None
    
    signal_line = calculate_ema(macd_series, signal_period)
    macd_line = macd_series[-1]
    
    if signal_line is None:
        return None
    
    histogram = macd_line - signal_line
    
    return {
        "macd": round(macd_line, 6),
        "signal": round(signal_line, 6),
        "hist": round(histogram, 6)
    }


def is_bullish_engulfing(c1: Dict[str, float], c2: Dict[str, float]) -> bool:
    """Check for bullish engulfing pattern."""
    try:
        c1_open = safe_float(c1.get("open"))
        c1_close = safe_float(c1.get("close"))
        c2_open = safe_float(c2.get("open"))
        c2_close = safe_float(c2.get("close"))
        
        if None in [c1_open, c1_close, c2_open, c2_close]:
            return False
        
        if c1_close >= c1_open:
            return False
        
        if c2_close <= c2_open:
            return False
        
        return (c2_open <= c1_close) and (c2_close >= c1_open)
    
    except Exception:
        return False


async def load_screener_data(symbol: str, interval: str = "1h") -> Dict[str, Any]:
    """
    Load all screener data for a symbol using Binance API.
    
    Features DNS fallback for network issues.
    """
    complete_cache_key = f"screener_complete:{symbol}:{interval}"
    cached_result = _get_from_cache(complete_cache_key)
    if cached_result is not None:
        return cached_result
    
    # Initialize data structure
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

    # Fetch OHLCV data
    candles = await get_binance_ohlcv(symbol, interval, 200)
    daily_candles = await get_binance_ohlcv(symbol, "1d", 10)
    
    if not candles or len(candles) < 50:
        _set_cache(complete_cache_key, data)
        return data
    
    # Extract basic data
    try:
        data["close"] = safe_float(candles[0].get("close"))
        data["prev_close"] = safe_float(candles[1].get("close")) if len(candles) > 1 else None
        data["volume"] = safe_float(candles[0].get("volume"))
        
        # Volume MA
        if len(candles) >= 20:
            volumes = [safe_float(c.get("volume"), 0) for c in candles[:20]]
            volumes = [v for v in volumes if v > 0]
            if len(volumes) >= 10:
                data["volume_ma"] = sum(volumes) / len(volumes)
        
        # Candles for patterns
        if len(candles) >= 2:
            data["candle_1"] = {
                "open": safe_float(candles[1].get("open")),
                "close": safe_float(candles[1].get("close")),
                "high": safe_float(candles[1].get("high")),
                "low": safe_float(candles[1].get("low"))
            }
            data["candle_2"] = {
                "open": safe_float(candles[0].get("open")),
                "close": safe_float(candles[0].get("close")),
                "high": safe_float(candles[0].get("high")),
                "low": safe_float(candles[0].get("low"))
            }
            
            data["bullish_engulfing"] = is_bullish_engulfing(data["candle_1"], data["candle_2"])
        
    except Exception as e:
        print(f"[screener] Error extracting basic data for {symbol}: {e}")
    
    # Prepare price arrays
    closes_newest_first = [safe_float(c.get("close")) for c in candles]
    closes_newest_first = [c for c in closes_newest_first if c is not None]
    closes_oldest_first = list(reversed(closes_newest_first))
    
    # Calculate indicators
    if len(closes_oldest_first) >= 200:
        data["rsi"] = calculate_rsi(closes_oldest_first, 14)
        data["ema20"] = calculate_ema(closes_oldest_first, 20)
        data["ema50"] = calculate_ema(closes_oldest_first, 50)
        data["ema200"] = calculate_ema(closes_oldest_first, 200)
        
        macd_result = calculate_macd(closes_oldest_first, 12, 26, 9)
        if macd_result:
            data["macd"] = macd_result["macd"]
            data["signal"] = macd_result["signal"]
            data["hist"] = macd_result["hist"]
    
    # Process daily data
    if daily_candles and len(daily_candles) >= 7:
        try:
            closes_7d = [safe_float(c.get("close")) for c in daily_candles[:7]]
            closes_7d = [c for c in closes_7d if c is not None]
            
            if len(closes_7d) >= 5:
                data["avg_7d"] = sum(closes_7d) / len(closes_7d)
            
            if len(daily_candles) >= 5:
                highs = [safe_float(c.get("high")) for c in daily_candles[:5]]
                lows = [safe_float(c.get("low")) for c in daily_candles[:5]]
                
                highs = [h for h in highs if h is not None]
                lows = [l for l in lows if l is not None]
                
                if highs:
                    data["resistance"] = max(highs)
                if lows:
                    data["support"] = min(lows)
        
        except Exception as e:
            print(f"[screener] Error processing daily data for {symbol}: {e}")
    
    # Cache result
    _set_cache(complete_cache_key, data)
    
    return data
