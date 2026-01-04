import asyncio
import json
import os
import time
from typing import Dict, List, Optional, Tuple
from decimal import Decimal, InvalidOperation
import httpx
from dotenv import load_dotenv


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IDS_PATH = os.path.join(BASE_DIR, "top100_coingecko_ids.json")

# API Configuration
load_dotenv()
CMC_API_KEY = os.getenv("CMC_API_KEY", "")
TWELVE_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")

# CoinMarketCap endpoints
CMC_BASE_URL = "https://pro-api.coinmarketcap.com/v1"
CMC_QUOTES_URL = f"{CMC_BASE_URL}/cryptocurrency/quotes/latest"

# Twelve Data config
TWELVE_BASE_URL = "https://api.twelvedata.com/time_series"
EXCHANGE = "binance"

# Rate limiting configuration (20 requests per minute)
RATE_LIMIT_REQUESTS = 20
RATE_LIMIT_PERIOD = 60  # seconds
_rate_limit_queue = []

# Cache configuration (10 minutes)
CACHE_DURATION = 600  # 10 minutes in seconds
_cache_store = {}

# Top 100 coins only
MAX_COINS = 100


# -----------------------------
# Rate Limiting
# -----------------------------

async def rate_limit():
    """Enforce rate limit of 20 requests per minute."""
    global _rate_limit_queue
    
    current_time = time.time()
    
    # Remove requests older than 60 seconds
    _rate_limit_queue = [t for t in _rate_limit_queue if current_time - t < RATE_LIMIT_PERIOD]
    
    # If we've hit the limit, wait
    if len(_rate_limit_queue) >= RATE_LIMIT_REQUESTS:
        oldest_request = _rate_limit_queue[0]
        wait_time = RATE_LIMIT_PERIOD - (current_time - oldest_request)
        if wait_time > 0:
            await asyncio.sleep(wait_time)
            return await rate_limit()  # Recursive call after waiting
    
    # Add current request to queue
    _rate_limit_queue.append(current_time)


# -----------------------------
# Cache Management
# -----------------------------

def get_cache_key(symbol: str, timeframe: str, source: str = "combined") -> str:
    """Generate cache key for a symbol/timeframe combination."""
    return f"{source}:{symbol}:{timeframe}"


def get_cached_data(cache_key: str) -> Optional[Dict]:
    """Retrieve cached data if still valid (within 10 minutes)."""
    if cache_key in _cache_store:
        data, timestamp = _cache_store[cache_key]
        if time.time() - timestamp < CACHE_DURATION:
            return data
        else:
            del _cache_store[cache_key]
    return None


def set_cached_data(cache_key: str, data: Dict) -> None:
    """Store data in cache with current timestamp."""
    _cache_store[cache_key] = (data, time.time())


# -----------------------------
# Load Top 100 Coins
# -----------------------------

def load_top_coins(limit: int = 100) -> List[Dict[str, str]]:
    """Load top 100 coins from top100_coingecko_ids.json file."""
    if not os.path.exists(IDS_PATH):
        raise FileNotFoundError(f"Coin IDs file not found: {IDS_PATH}")
    
    try:
        with open(IDS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"Invalid JSON in {IDS_PATH}: {e}", e.doc, e.pos)
    
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict in {IDS_PATH}, got {type(data)}")
    
    coins = []
    for symbol, coin_id in data.items():
        if not symbol or not coin_id:
            continue
        
        symbol_upper = symbol.upper()
        coins.append({"symbol": symbol_upper, "id": coin_id})
    
    return coins[:limit]


# -----------------------------
# Indicator Calculation Helpers
# -----------------------------

def safe_divide(numerator: float, denominator: float, default: Optional[float] = None) -> Optional[float]:
    """Safely divide two numbers."""
    try:
        if denominator == 0 or abs(denominator) < 1e-10:
            return default
        return numerator / denominator
    except (TypeError, ValueError, ZeroDivisionError):
        return default


def calculate_ema(prices: List[float], period: int) -> Optional[float]:
    """Calculate Exponential Moving Average."""
    if len(prices) < period:
        return None
    
    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    
    return ema


def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """Calculate Relative Strength Index."""
    if len(prices) < period + 1:
        return None
    
    gains = []
    losses = []
    
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))
    
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def calculate_macd(prices: List[float]) -> tuple:
    """Calculate MACD, Signal, and Histogram."""
    if len(prices) < 26:
        return None, None, None
    
    ema12 = calculate_ema(prices, 12)
    ema26 = calculate_ema(prices, 26)
    
    if ema12 is None or ema26 is None:
        return None, None, None
    
    macd = ema12 - ema26
    
    macd_values = []
    for i in range(26, len(prices)):
        e12 = calculate_ema(prices[:i+1], 12)
        e26 = calculate_ema(prices[:i+1], 26)
        if e12 and e26:
            macd_values.append(e12 - e26)
    
    if len(macd_values) < 9:
        return macd, None, None
    
    signal = calculate_ema(macd_values, 9)
    hist = macd - signal if signal else None
    
    return macd, signal, hist


def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Optional[float]:
    """Calculate Average True Range."""
    if len(highs) < period + 1:
        return None
    
    true_ranges = []
    for i in range(1, len(highs)):
        high_low = highs[i] - lows[i]
        high_close = abs(highs[i] - closes[i-1])
        low_close = abs(lows[i] - closes[i-1])
        true_ranges.append(max(high_low, high_close, low_close))
    
    return sum(true_ranges[-period:]) / period


def normalize_macd(macd: float, signal: float) -> Optional[float]:
    """Normalize MACD relative to signal line."""
    result = safe_divide(macd - signal, abs(signal))
    if result is not None:
        return round(result, 4)
    return None


def price_distance(price: float, ema: float) -> Optional[float]:
    """Calculate percentage distance of price from EMA."""
    result = safe_divide(price - ema, ema)
    if result is not None:
        return round(result * 100, 2)
    return None


def atr_percent(atr: float, price: float) -> Optional[float]:
    """Calculate ATR as percentage of price."""
    result = safe_divide(atr, price)
    if result is not None:
        return round(result * 100, 2)
    return None


def detect_trend(rsi: float, macd_norm: float) -> str:
    """Detect market trend based on RSI and normalized MACD."""
    if not (0 <= rsi <= 100):
        return "range"
    
    if rsi > 55 and macd_norm > 0:
        return "bull"
    if rsi < 45 and macd_norm < 0:
        return "bear"
    return "range"


def detect_volatility(atr_pct: float) -> str:
    """Detect volatility level based on ATR percentage."""
    if atr_pct < 0:
        return "unknown"
    
    if atr_pct < 1:
        return "low"
    if atr_pct < 3:
        return "medium"
    return "high"


# -----------------------------
# CoinMarketCap API Functions
# -----------------------------

async def fetch_cmc_data(symbol: str, timeframe: str = "1h", debug: bool = False) -> Optional[Dict]:
    """
    Fetch current data from CoinMarketCap API.
    Note: CMC doesn't provide historical OHLCV in the free tier,
    so we fetch current quotes and use Twelve Data for historical data.
    """
    cache_key = get_cache_key(symbol, timeframe, "cmc")
    cached = get_cached_data(cache_key)
    if cached:
        if debug:
            print(f"✓ Cache hit for {symbol} (CMC)")
        return cached
    
    if not CMC_API_KEY:
        if debug:
            print(f"⚠️ No CMC API key provided")
        return None
    
    await rate_limit()
    
    params = {
        "symbol": symbol,
        "convert": "USD"
    }
    
    headers = {
        "X-CMC_PRO_API_KEY": CMC_API_KEY,
        "Accept": "application/json"
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(CMC_QUOTES_URL, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        
        if data.get("status", {}).get("error_code") == 0 and "data" in data:
            if symbol in data["data"]:
                result = {"quote": data["data"][symbol], "source": "cmc"}
                set_cached_data(cache_key, result)
                if debug:
                    print(f"✓ CMC data fetched for {symbol}")
                return result
        
        if debug:
            print(f"⚠️ CMC returned no data for {symbol}")
        return None
    
    except httpx.HTTPStatusError as e:
        if debug:
            print(f"❌ CMC API error for {symbol}: {e.response.status_code}")
        return None
    except Exception as e:
        if debug:
            print(f"❌ CMC fetch error for {symbol}: {type(e).__name__}: {e}")
        return None


# -----------------------------
# Twelve Data API Functions (Fallback for Historical OHLCV)
# -----------------------------

def normalize_symbol_twelve(symbol: str) -> str:
    """Convert BTC → BTCUSDT for Twelve Data."""
    return f"{symbol}USDT"


async def fetch_twelve_ohlcv(symbol: str, timeframe: str = "1h", outputsize: int = 100, debug: bool = False) -> Optional[Dict]:
    """Fetch OHLCV data from Twelve Data API (fallback for historical data)."""
    cache_key = get_cache_key(symbol, timeframe, "twelve")
    cached = get_cached_data(cache_key)
    if cached:
        if debug:
            print(f"✓ Cache hit for {symbol} (Twelve)")
        return cached
    
    if not TWELVE_API_KEY:
        if debug:
            print(f"⚠️ No Twelve Data API key provided")
        return None
    
    await rate_limit()
    
    normalized = normalize_symbol_twelve(symbol)
    
    params = {
        "symbol": normalized,
        "interval": timeframe,
        "outputsize": outputsize,
        "exchange": EXCHANGE,
        "apikey": TWELVE_API_KEY,
        "format": "JSON"
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(TWELVE_BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        
        if isinstance(data, dict) and "values" in data and data["values"]:
            result = {"values": data["values"], "source": "twelve"}
            set_cached_data(cache_key, result)
            if debug:
                print(f"✓ Twelve Data fetched for {symbol}")
            return result
        
        if debug:
            print(f"⚠️ Twelve Data returned no values for {symbol}")
        return None
    
    except httpx.HTTPStatusError as e:
        if debug:
            print(f"❌ Twelve Data API error for {symbol}: {e.response.status_code}")
        return None
    except Exception as e:
        if debug:
            print(f"❌ Twelve Data fetch error for {symbol}: {type(e).__name__}: {e}")
        return None


# -----------------------------
# Process OHLCV to Indicators
# -----------------------------

def process_ohlcv_to_indicators(symbol: str, ohlcv_data: Dict, cmc_data: Optional[Dict], timeframe: str) -> Optional[Dict]:
    """Process OHLCV format to indicators, using CMC for current price if available."""
    try:
        values = ohlcv_data.get("values", [])
        if not values:
            return None
        
        # Twelve Data format: reverse to get chronological order
        candles = list(reversed(values))
        
        closes = [float(c["close"]) for c in candles]
        highs = [float(c["high"]) for c in candles]
        lows = [float(c["low"]) for c in candles]
        
        # Use CMC current price if available, otherwise use latest close
        if cmc_data and "quote" in cmc_data:
            last_price = float(cmc_data["quote"]["quote"]["USD"]["price"])
            source = "cmc+twelve"
        else:
            last_price = closes[-1]
            source = "twelve"
        
        return calculate_indicators_from_prices(symbol, timeframe, closes, highs, lows, last_price, source)
    
    except Exception as e:
        print(f"⚠️ Indicator processing error for {symbol}: {e}")
        return None


def calculate_indicators_from_prices(
    symbol: str, 
    timeframe: str, 
    closes: List[float], 
    highs: List[float], 
    lows: List[float],
    last_price: float,
    source: str
) -> Optional[Dict]:
    """Calculate all indicators from price arrays."""
    try:
        ema20 = calculate_ema(closes, 20)
        rsi = calculate_rsi(closes)
        macd, macd_signal, macd_hist = calculate_macd(closes)
        atr = calculate_atr(highs, lows, closes)
        
        if any(v is None for v in [ema20, rsi, macd, macd_signal, atr]):
            return None
        
        macd_norm = normalize_macd(macd, macd_signal)
        if macd_norm is None:
            return None
        
        ema_dist = price_distance(last_price, ema20)
        atr_pct = atr_percent(atr, last_price)
        
        if ema_dist is None or atr_pct is None:
            return None
        
        trend = detect_trend(rsi, macd_norm)
        volatility = detect_volatility(atr_pct)
        
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "price": round(last_price, 6),
            "rsi": round(rsi, 2),
            "macd_norm": macd_norm,
            "price_vs_ema20_pct": ema_dist,
            "atr_pct": atr_pct,
            "trend": trend,
            "volatility": volatility,
            "source": source,
            "extras": {
                "macdHist": round(macd_hist, 2),
            }
        }
    
    except Exception as e:
        print(f"⚠️ Indicator calculation error for {symbol}: {e}")
        return None


# -----------------------------
# Main Function
# -----------------------------

async def fetch_top_100_indicator_data(
    timeframe: str = "1h",
    debug: bool = False
) -> List[Dict]:
    """
    Fetch indicator data for top 100 coins using CMC API with Twelve Data fallback.
    - Rate limited to 20 requests/minute
    - Results cached for 10 minutes
    - Uses CoinMarketCap for current prices
    - Falls back to Twelve Data for historical OHLCV when needed
    """
    try:
        coins = load_top_coins(MAX_COINS)
        
        if not coins:
            print("⚠️ No coins loaded from top100_coingecko_ids.json")
            return []
        
        print(f"📊 Fetching indicators for {len(coins)} coins...")
        print(f"   Primary: CoinMarketCap API (current quotes)")
        print(f"   Fallback: Twelve Data API (historical OHLCV)")
        print(f"   Rate Limit: {RATE_LIMIT_REQUESTS} requests/min")
        print(f"   Cache Duration: {CACHE_DURATION//60} minutes")
        
        all_results = []
        cmc_count = 0
        twelve_count = 0
        cache_count = 0
        combined_count = 0
        
        for coin in coins:
            symbol = coin["symbol"]
            
            # Check cache first
            cache_key_combined = get_cache_key(symbol, timeframe, "combined")
            if get_cached_data(cache_key_combined):
                cache_count += 1
            
            # Try to get CMC current price (for real-time data)
            cmc_data = await fetch_cmc_data(symbol, timeframe, debug=debug)
            
            # Get historical OHLCV from Twelve Data (needed for indicators)
            twelve_data = await fetch_twelve_ohlcv(symbol, timeframe, debug=debug)
            
            if twelve_data:
                # Process indicators using Twelve Data OHLCV
                result = process_ohlcv_to_indicators(symbol, twelve_data, cmc_data, timeframe)
                
                if result:
                    all_results.append(result)
                    
                    # Track source
                    if result["source"] == "cmc+twelve":
                        combined_count += 1
                    elif result["source"] == "cmc":
                        cmc_count += 1
                    else:
                        twelve_count += 1
                    
                    # Cache the result
                    set_cached_data(cache_key_combined, result)
            
            elif debug:
                print(f"⚠️ No data available for {symbol}")
        
        success_rate = (len(all_results) / len(coins) * 100) if coins else 0
        print(f"\n✅ Successfully fetched {len(all_results)}/{len(coins)} coins ({success_rate:.1f}%)")
        print(f"   CMC+Twelve: {combined_count} | Twelve only: {twelve_count} | Cached: {cache_count}")
        print(f"   Total API calls: ~{len(_rate_limit_queue)}")
        
        return all_results
    
    except Exception as e:
        print(f"❌ Fatal error: {type(e).__name__}: {e}")
        import traceback
        if debug:
            print(traceback.format_exc())
        return []


# -----------------------------
# Clear Cache Function
# -----------------------------

def clear_cache():
    """Manually clear all cached data."""
    global _cache_store, _rate_limit_queue
    _cache_store.clear()
    _rate_limit_queue.clear()
    print("✓ Cache and rate limit queue cleared")


# -----------------------------
# Example Usage
# -----------------------------

async def main():
    """Example usage of the indicator fetcher."""
    results = await fetch_top_100_indicator_data(timeframe="1h", debug=True)
    
    if results:
        print(f"\n📈 Sample Results:")
        for result in results[:5]:
            print(f"   {result['symbol']}: ${result['price']} | RSI: {result['rsi']} | Trend: {result['trend']} | Source: {result['source']}")


if __name__ == "__main__":
    asyncio.run(main())