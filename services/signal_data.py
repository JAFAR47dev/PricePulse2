import asyncio
import json
import os
from typing import Dict, List, Optional
from decimal import Decimal, InvalidOperation
import httpx

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IDS_PATH = os.path.join(BASE_DIR, "coingecko_ids.json")

# Your API configuration
TWELVE_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
BATCH_BASE_URL = "https://api.twelvedata.com/time_series"

# Cache to avoid repeated calculations
_indicator_cache = {}


# -----------------------------
# Load Top Coins
# -----------------------------

# Major coins typically supported by TwelveData API
SUPPORTED_SYMBOLS = {
    'BTC', 'ETH', 'BNB', 'XRP', 'ADA', 'DOGE', 'SOL', 'TRX', 'DOT', 'MATIC',
    'LTC', 'SHIB', 'AVAX', 'UNI', 'LINK', 'XLM', 'ATOM', 'ETC', 'FIL', 'HBAR',
    'APT', 'ARB', 'OP', 'NEAR', 'VET', 'ALGO', 'ICP', 'QNT', 'GRT', 'SAND',
    'MANA', 'XMR', 'AAVE', 'MKR', 'EOS', 'FTM', 'AXS', 'THETA', 'XTZ', 'EGLD',
    'FLOW', 'CHZ', 'KLAY', 'RUNE', 'ZEC', 'DASH', 'COMP', 'SNX', 'YFI', 'CRV',
    'SUSHI', '1INCH', 'ENJ', 'BAT', 'ZIL', 'HOT', 'ICX', 'ONT', 'ZRX', 'QTUM',
}


def load_top_coins(limit: int = 200, filter_supported: bool = True) -> List[Dict[str, str]]:
    """Load top coins from coingecko_ids.json file."""
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
        
        if filter_supported and symbol_upper not in SUPPORTED_SYMBOLS:
            continue
        
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
    
    # Calculate signal line (9-period EMA of MACD)
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


def validate_numeric(value: any, min_val: float = None, max_val: float = None) -> bool:
    """Validate that a value is numeric and within optional bounds."""
    try:
        num = float(value)
        
        if not (num == num):  # NaN check
            return False
        if num == float('inf') or num == float('-inf'):
            return False
        
        if min_val is not None and num < min_val:
            return False
        if max_val is not None and num > max_val:
            return False
        
        return True
    except (TypeError, ValueError, InvalidOperation):
        return False


import json
import time
import httpx
from typing import List, Dict, Optional

# -----------------------------
# CONFIG
# -----------------------------
BATCH_BASE_URL = "https://api.twelvedata.com/time_series"
MAX_BATCH_SIZE = 100  # Safe limit (<120)
EXCHANGE = "binance"

# -----------------------------
# Helpers
# -----------------------------
def chunked(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def normalize_symbol(symbol: str) -> str:
    """
    Convert BTC/USD → BTCUSDT (Binance-native)
    """
    if symbol.endswith("/USD"):
        return symbol.replace("/USD", "USDT")
    return symbol.replace("/", "")


# -----------------------------
# BATCH OHLCV FETCHER
# -----------------------------
async def fetch_batch_ohlcv_data(
    symbols: List[str],
    timeframe: str = "1h",
    outputsize: int = 100,
    debug: bool = False
) -> Dict[str, Dict]:
    """
    Fetch OHLCV data for multiple symbols using TwelveData batch endpoint.
    Uses Binance exchange + USDT pairs for maximum coverage.
    """

    all_results: Dict[str, Dict] = {}

    for batch in chunked(symbols, MAX_BATCH_SIZE):
        normalized = [normalize_symbol(s) for s in batch]
        symbol_string = ",".join(normalized)

        params = {
            "symbol": symbol_string,
            "interval": timeframe,
            "outputsize": outputsize,
            "exchange": EXCHANGE,          # ✅ REQUIRED
            "apikey": TWELVE_API_KEY,
            "format": "JSON",
        }

        if debug:
            print(f"🌐 Batch request ({len(batch)} symbols)")
            print(f"   Exchange: {EXCHANGE}")
            print(f"   Symbols: {symbol_string[:120]}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(BATCH_BASE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()

            # -----------------------------
            # RESPONSE PARSING
            # -----------------------------
            if len(batch) == 1:
                if isinstance(data, dict) and "values" in data:
                    all_results[batch[0]] = data
                elif debug:
                    print(f"⚠️ No values for {batch[0]}")
            else:
                for fmt, original in zip(normalized, batch):
                    if (
                        isinstance(data, dict)
                        and fmt in data
                        and isinstance(data[fmt], dict)
                        and "values" in data[fmt]
                        and data[fmt]["values"]
                    ):
                        all_results[original] = data[fmt]
                    elif debug:
                        print(f"⚠️ Missing values for {original}")

        except httpx.HTTPStatusError as e:
            print(f"❌ API error {e.response.status_code}: {e.response.text[:200]}")
        except Exception as e:
            print(f"❌ Batch fetch error: {type(e).__name__}: {e}")

        # Soft rate limit protection
        await asyncio.sleep(0.5)

    return all_results    
    
# -----------------------------
# OHLCV → INDICATORS
# -----------------------------
def process_ohlcv_to_indicators(
    symbol: str,
    ohlcv_data: Dict,
    timeframe: str
) -> Optional[Dict]:
    """
    Convert OHLCV candles into a normalized indicator pack.
    """

    try:
        values = ohlcv_data.get("values")
        if not values:
            return None

        candles = list(reversed(values))

        closes = [float(c["close"]) for c in candles]
        highs  = [float(c["high"]) for c in candles]
        lows   = [float(c["low"]) for c in candles]

        # --- Indicator calculations ---
        ema20 = calculate_ema(closes, 20)
        rsi   = calculate_rsi(closes)
        macd, macd_signal, macd_hist = calculate_macd(closes)
        atr   = calculate_atr(highs, lows, closes)

        # --- Mandatory enforcement ---
        if any(v is None for v in [ema20, rsi, macd, macd_signal, atr]):
            return None

        last_price = closes[-1]

        macd_norm = normalize_macd(macd, macd_signal)
        if macd_norm is None:
            return None

        ema_dist = price_distance(last_price, ema20)
        atr_pct  = atr_percent(atr, last_price)

        if ema_dist is None or atr_pct is None:
            return None

        # --- Context ---
        trend = detect_trend(rsi, macd_norm)
        volatility = detect_volatility(atr_pct)

        return {
            "symbol": symbol.replace("/USDT", "").replace("/USD", ""),
            "timeframe": timeframe,
            "price": round(last_price, 6),
            "rsi": round(rsi, 2),
            "macd_norm": macd_norm,
            "price_vs_ema20_pct": ema_dist,
            "atr_pct": atr_pct,
            "trend": trend,
            "volatility": volatility,
            "extras": {
                "macdHist": round(macd_hist, 2),
            }
        }

    except Exception as e:
        print(f"⚠️ Indicator processing error for {symbol}: {e}")
        return None

# -----------------------------
# Main Function - Fetch All Coins in Batches
# -----------------------------

async def fetch_top_200_indicator_data(
    timeframe: str = "1h",
    limit: int = 200,
    filter_supported: bool = True,
    batch_size: int = 100,
    debug: bool = True  # Default to True for now
) -> List[Dict]:
    """
    Fetch indicator data for top coins using BATCH API calls.
    
    This dramatically reduces API credits by fetching multiple symbols per request.
    
    Args:
        timeframe: Timeframe for indicators (e.g., '1h', '4h', '1d')
        limit: Maximum number of coins to fetch
        filter_supported: Only fetch data for known supported symbols
        batch_size: Number of symbols per API call (max 120 for TwelveData)
        debug: Enable debug output to see API response structure
        
    Returns:
        List of valid indicator packs
    """
    try:
        coins = load_top_coins(limit, filter_supported=filter_supported)
        
        if not coins:
            print("⚠️ No coins loaded")
            return []
        
        # Prepare symbol list
        symbols = [f"{coin['symbol']}/USD" for coin in coins]
        
        print(f"📊 Fetching indicators for {len(symbols)} coins using BATCH API...")
        print(f"   API calls needed: {(len(symbols) + batch_size - 1) // batch_size}")
        
        if debug:
            print(f"   Debug mode enabled")
            print(f"   Sample symbols: {', '.join(symbols[:5])}")
        
        all_results = []
        
        # Process in batches
        for i in range(0, len(symbols), batch_size):
            batch_symbols = symbols[i:i + batch_size]
            
            print(f"\n📦 Batch {i//batch_size + 1}: Fetching {len(batch_symbols)} symbols...")
            
            # Single API call for entire batch - PASS DEBUG PARAMETER
            ohlcv_data = await fetch_batch_ohlcv_data(batch_symbols, timeframe, debug=debug)
            
            if debug:
                print(f"   Received data for {len(ohlcv_data)} symbols")
            
            # Process each symbol's data
            processed_count = 0
            for symbol in batch_symbols:
                if symbol in ohlcv_data:
                    result = process_ohlcv_to_indicators(symbol, ohlcv_data[symbol], timeframe)
                    if result:
                        all_results.append(result)
                        processed_count += 1
                    elif debug:
                        print(f"⚠️ Failed to process indicators for {symbol}")
                elif debug:
                    print(f"⚠️ No data received for {symbol}")
            
            if debug:
                print(f"   Successfully processed {processed_count}/{len(batch_symbols)} symbols")
            
            # Rate limiting: wait between batches
            if i + batch_size < len(symbols):
                if debug:
                    print(f"   Waiting 1 second before next batch...")
                await asyncio.sleep(1)
        
        success_rate = (len(all_results) / len(symbols) * 100) if symbols else 0
        print(f"\n✅ Successfully fetched {len(all_results)}/{len(symbols)} coins ({success_rate:.1f}%)")
        
        if len(all_results) == 0 and not debug:
            print("\n💡 Run with debug=True to see API response structure:")
            print("   await fetch_top_200_indicator_data(debug=True)")
        
        return all_results
    
    except Exception as e:
        print(f"❌ Fatal error: {type(e).__name__}: {e}")
        import traceback
        if debug:
            print(traceback.format_exc())
        return []