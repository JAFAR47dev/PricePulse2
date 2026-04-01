# services/screener_data.py - Multi-exchange version (Bybit + OKX)
import aiohttp
import os
import asyncio
import time
from datetime import datetime
from dotenv import load_dotenv
from typing import Optional, Dict, Any, List
from collections import deque

load_dotenv()

# ============================================================================
# EXCHANGE ENDPOINTS
# ============================================================================

BYBIT_ENDPOINTS = [
    "https://api.bybit.com",
    "https://api.bytick.com",  # Backup domain
]

OKX_ENDPOINTS = [
    "https://www.okx.com",
    "https://aws.okx.com",  # AWS backup
]

# Configuration
REQUEST_TIMEOUT = 10
MAX_RETRIES = 2
CACHE_TTL = 3600 # 1 hour

# Rate limiting
RATE_LIMIT_WINDOW = 60
MAX_REQUESTS_PER_WINDOW = 400  # More conservative for multiple exchanges
_request_times: deque = deque(maxlen=MAX_REQUESTS_PER_WINDOW)
_rate_limit_lock = asyncio.Lock()
_cache: Dict[str, tuple[Any, float]] = {}
_working_bybit = None
_working_okx = None


# ============================================================================
# RATE LIMITING & CACHING
# ============================================================================

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


def _get_cache_key(symbol: str, interval: str, exchange: str, params: str = "") -> str:
    """Generate unique cache key."""
    return f"{exchange}:{symbol}:{interval}:{params}"


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
    global _working_bybit, _working_okx
    _cache.clear()
    _working_bybit = None
    _working_okx = None


# ============================================================================
# SYMBOL NORMALIZATION
# ============================================================================

def normalize_symbol_for_bybit(symbol: str) -> str:
    """Convert symbol to Bybit format (e.g., BTCUSDT)"""
    symbol = symbol.strip().upper()
    symbol = symbol.replace("/", "")
    
    if symbol.endswith("USDT"):
        return symbol
    
    if symbol.endswith("USD"):
        return symbol[:-3] + "USDT"
    
    return symbol + "USDT"


def normalize_symbol_for_okx(symbol: str) -> str:
    """Convert symbol to OKX format (e.g., BTC-USDT)"""
    symbol = symbol.strip().upper()
    
    # Remove existing separators
    symbol = symbol.replace("/", "").replace("-", "")
    
    # Add USDT if needed
    if not symbol.endswith("USDT") and not symbol.endswith("USD"):
        symbol = symbol + "USDT"
    
    if symbol.endswith("USD") and not symbol.endswith("USDT"):
        symbol = symbol[:-3] + "USDT"
    
    # Insert hyphen before USDT
    if symbol.endswith("USDT"):
        base = symbol[:-4]
        return f"{base}-USDT"
    
    return symbol


def interval_to_bybit(interval: str) -> str:
    """Map interval to Bybit format"""
    mapping = {
        "1m": "1",
        "5m": "5",
        "15m": "15",
        "30m": "30",
        "1h": "60",
        "2h": "120",
        "4h": "240",
        "1d": "D",
        "1day": "D",
        "daily": "D",
    }
    return mapping.get(interval, interval)


def interval_to_okx(interval: str) -> str:
    """Map interval to OKX format"""
    mapping = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1h": "1H",
        "2h": "2H",
        "4h": "4H",
        "1d": "1D",
        "1day": "1D",
        "daily": "1D",
    }
    return mapping.get(interval, interval)


# ============================================================================
# BYBIT API
# ============================================================================

async def fetch_bybit_klines(symbol: str, interval: str = "60", limit: int = 200) -> Optional[List[Dict]]:
    """
    Fetch klines from Bybit V5 API
    
    Docs: https://bybit-exchange.github.io/docs/v5/market/kline
    """
    global _working_bybit
    
    bybit_symbol = normalize_symbol_for_bybit(symbol)
    bybit_interval = interval_to_bybit(interval)
    
    # Calculate start time (Bybit uses milliseconds)
    # Fetch extra candles to ensure we have enough
    intervals_ms = {
        "1": 60 * 1000,
        "5": 5 * 60 * 1000,
        "15": 15 * 60 * 1000,
        "30": 30 * 60 * 1000,
        "60": 60 * 60 * 1000,
        "240": 4 * 60 * 60 * 1000,
        "D": 24 * 60 * 60 * 1000,
    }
    
    interval_ms = intervals_ms.get(bybit_interval, 60 * 60 * 1000)
    end_time = int(time.time() * 1000)
    start_time = end_time - (limit * interval_ms)
    
    params = {
        "category": "spot",
        "symbol": bybit_symbol,
        "interval": bybit_interval,
        "start": start_time,
        "end": end_time,
        "limit": min(limit, 1000)
    }
    
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    
    # Try working endpoint first
    endpoints = [_working_bybit] if _working_bybit else []
    endpoints.extend([e for e in BYBIT_ENDPOINTS if e not in endpoints])
    
    for base_url in endpoints:
        url = f"{base_url}/v5/market/kline"
        
        try:
            connector = aiohttp.TCPConnector(force_close=True, ttl_dns_cache=300)
            
            async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        if data.get("retCode") == 0 and data.get("result", {}).get("list"):
                            _working_bybit = base_url
                            
                            # Convert Bybit format
                            klines = []
                            for k in reversed(data["result"]["list"]):  # Bybit returns newest first
                                klines.append({
                                    "datetime": datetime.fromtimestamp(int(k[0]) / 1000).isoformat(),
                                    "open": float(k[1]),
                                    "high": float(k[2]),
                                    "low": float(k[3]),
                                    "close": float(k[4]),
                                    "volume": float(k[5])
                                })
                            
                            return klines
                        
                        print(f"[Bybit] API error: {data.get('retMsg', 'Unknown error')}")
                        continue
        
        except Exception as e:
            print(f"[Bybit] Error with {base_url}: {e}")
            continue
    
    return None


# ============================================================================
# OKX API
# ============================================================================

async def fetch_okx_klines(symbol: str, interval: str = "1H", limit: int = 200) -> Optional[List[Dict]]:
    """
    Fetch klines from OKX API
    
    Docs: https://www.okx.com/docs-v5/en/#rest-api-market-data-get-candlesticks
    """
    global _working_okx
    
    okx_symbol = normalize_symbol_for_okx(symbol)
    okx_interval = interval_to_okx(interval)
    
    params = {
        "instId": okx_symbol,
        "bar": okx_interval,
        "limit": min(limit, 300)  # OKX max is 300
    }
    
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    
    # Try working endpoint first
    endpoints = [_working_okx] if _working_okx else []
    endpoints.extend([e for e in OKX_ENDPOINTS if e not in endpoints])
    
    for base_url in endpoints:
        url = f"{base_url}/api/v5/market/candles"
        
        try:
            connector = aiohttp.TCPConnector(force_close=True, ttl_dns_cache=300)
            
            async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        if data.get("code") == "0" and data.get("data"):
                            _working_okx = base_url
                            
                            # Convert OKX format
                            klines = []
                            for k in reversed(data["data"]):  # OKX returns newest first
                                klines.append({
                                    "datetime": datetime.fromtimestamp(int(k[0]) / 1000).isoformat(),
                                    "open": float(k[1]),
                                    "high": float(k[2]),
                                    "low": float(k[3]),
                                    "close": float(k[4]),
                                    "volume": float(k[5])
                                })
                            
                            return klines
                        
                        print(f"[OKX] API error: {data.get('msg', 'Unknown error')}")
                        continue
        
        except Exception as e:
            print(f"[OKX] Error with {base_url}: {e}")
            continue
    
    return None


# ============================================================================
# UNIFIED KLINE FETCHER
# ============================================================================

async def get_ohlcv(symbol: str, interval: str = "1h", limit: int = 200) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch OHLCV data with automatic fallback between Bybit and OKX
    
    Returns:
        List of candles (newest → oldest) or None
    """
    cache_key = _get_cache_key(symbol, interval, "multi_exchange", f"limit={limit}")
    
    # Check cache
    cached = _get_from_cache(cache_key)
    if cached:
        return cached
    
    await _wait_for_rate_limit()
    
    # Try Bybit first (generally more reliable for spot)
    print(f"[screener] Fetching {symbol} {interval} from Bybit...")
    candles = await fetch_bybit_klines(symbol, interval, limit)
    
    if candles and len(candles) >= 50:
        print(f"[screener] ✅ Got {len(candles)} candles from Bybit")
        candles.reverse()  # Convert to newest first
        _set_cache(cache_key, candles)
        return candles
    
    # Fallback to OKX
    print(f"[screener] Bybit failed, trying OKX...")
    candles = await fetch_okx_klines(symbol, interval, limit)
    
    if candles and len(candles) >= 50:
        print(f"[screener] ✅ Got {len(candles)} candles from OKX")
        candles.reverse()  # Convert to newest first
        _set_cache(cache_key, candles)
        return candles
    
    print(f"[screener] ❌ Both exchanges failed for {symbol}")
    return None


# ============================================================================
# INDICATOR CALCULATIONS (unchanged)
# ============================================================================

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


# ============================================================================
# MAIN SCREENER DATA LOADER
# ============================================================================

async def load_screener_data(symbol: str, interval: str = "1h") -> Dict[str, Any]:
    """
    Load all screener data for a symbol using Bybit/OKX APIs.
    
    Automatically falls back between exchanges if one fails.
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
    candles = await get_ohlcv(symbol, interval, 200)
    daily_candles = await get_ohlcv(symbol, "1d", 10)
    
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
