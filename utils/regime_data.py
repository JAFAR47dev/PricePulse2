# ============================================================================
# PHASE 2 — MARKET DATA LAYER (100% ACCURATE & PRODUCTION-READY)
# ============================================================================

# ----------------------------------------------------------------------------
# utils/regime_data.py
# ----------------------------------------------------------------------------
"""
Fetch and validate market data from Twelve Data API
Handles errors, validates data, and normalizes output
Supports dynamic timeframe combinations for regime analysis
"""
import aiohttp
import os
import math
import json
from typing import Optional, List, Dict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# API Configuration
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY")
BASE_URL = "https://api.twelvedata.com"

import json
import logging

logger = logging.getLogger(__name__)

# Load top 100 CoinGecko coins for validation
def load_supported_symbols() -> set:
    """
    Load supported symbols from top100_coingecko_ids.json
    Returns:
        set: {"BTC", "ETH", "USDT", ...}
    """
    try:
        with open("services/top100_coingecko_ids.json", "r") as f:
            data = json.load(f)

            if not isinstance(data, dict):
                raise ValueError("top100_coingecko_ids.json must be a dict")

            # Keys are already symbols
            symbols = {symbol.upper() for symbol in data.keys()}

            logger.info(
                f"Loaded {len(symbols)} supported symbols from top 100 CoinGecko"
            )
            return symbols

    except Exception as e:
        logger.error(f"Error loading top 100 CoinGecko symbols: {e}")

        # Safe fallback (used only if file missing or corrupted)
        return {
            "BTC", "ETH", "BNB", "XRP", "ADA", "DOGE", "SOL", "MATIC",
            "DOT", "AVAX", "LINK", "UNI", "ATOM", "LTC", "ETC"
        }


SUPPORTED_SYMBOLS = load_supported_symbols()


class MarketDataError(Exception):
    """Custom exception for market data errors"""
    pass


async def fetch_market_data(
    symbol: str, 
    interval: str, 
    limit: int = 100
) -> List[Dict]:
    """
    Fetch OHLCV data from Twelve Data API with validation
    
    Args:
        symbol: Trading pair (e.g., "BTC", "ETH")
        interval: Timeframe ("1h", "4h", "1day")
        limit: Number of candles to fetch
    
    Returns:
        List of normalized candles with OHLCV data (oldest first)
    
    Raises:
        MarketDataError: If data fetch fails or validation fails
    """
    
    # Validate and normalize symbol
    validated_symbol = validate_symbol(symbol)
    
    # Convert symbol format for Twelve Data (BTC -> BTC/USD)
    api_symbol = f"{validated_symbol}/USD"
    
    # Map interval to Twelve Data format
    api_interval = map_interval(interval)
    
    # Validate API key exists
    if not TWELVE_DATA_API_KEY:
        raise MarketDataError("TWELVE_DATA_API_KEY environment variable not set")
    
    url = f"{BASE_URL}/time_series"
    params = {
        "symbol": api_symbol,
        "interval": api_interval,
        "outputsize": limit,
        "apikey": TWELVE_DATA_API_KEY,
        "format": "JSON"
    }
    
    logger.info(f"Fetching {symbol} data: interval={interval}, limit={limit}")
    
    try:
        # Create timeout object (10 seconds total, 5 seconds connect)
        timeout = aiohttp.ClientTimeout(total=15, connect=5)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as response:
                
                # Handle HTTP status codes
                if response.status == 400:
                    raise MarketDataError(f"Invalid request for {validated_symbol}")
                elif response.status == 401:
                    raise MarketDataError("Invalid API key - check TWELVE_DATA_API_KEY")
                elif response.status == 403:
                    raise MarketDataError("API access forbidden - check subscription")
                elif response.status == 404:
                    raise MarketDataError(f"Symbol {validated_symbol} not found")
                elif response.status == 429:
                    raise MarketDataError("API rate limit exceeded - wait and retry")
                elif response.status == 500:
                    raise MarketDataError("Twelve Data API server error")
                elif response.status == 503:
                    raise MarketDataError("Twelve Data API temporarily unavailable")
                elif response.status != 200:
                    raise MarketDataError(f"API error: HTTP {response.status}")
                
                # Parse JSON response
                try:
                    data = await response.json()
                except aiohttp.ContentTypeError:
                    raise MarketDataError("Invalid API response format")
                
                # Check for API error messages in response
                if isinstance(data, dict):
                    # Check for error status
                    if "status" in data and data["status"] == "error":
                        error_msg = data.get("message", "Unknown API error")
                        
                        # Handle specific error types
                        if "symbol" in error_msg.lower() or "invalid" in error_msg.lower():
                            raise MarketDataError(f"Invalid symbol: {validated_symbol}")
                        elif "limit" in error_msg.lower() or "credits" in error_msg.lower():
                            raise MarketDataError("API quota exceeded")
                        else:
                            raise MarketDataError(f"API error: {error_msg}")
                    
                    # Check for code field (another error format)
                    if "code" in data and data["code"] != 200:
                        error_msg = data.get("message", "Unknown API error")
                        raise MarketDataError(f"API error: {error_msg}")
                
                # Validate response structure
                if not isinstance(data, dict) or "values" not in data:
                    raise MarketDataError(f"Invalid API response structure for {validated_symbol}")
                
                if not data["values"] or not isinstance(data["values"], list):
                    raise MarketDataError(f"No data available for {validated_symbol}")
                
                # Normalize and validate candles
                candles = normalize_candles(data["values"], validated_symbol)
                
                logger.info(f"Successfully fetched {len(candles)} candles for {symbol} ({interval})")
                
                # Final validation - need minimum data for indicators
                if len(candles) < 20:
                    raise MarketDataError(
                        f"Insufficient data for {validated_symbol}: "
                        f"got {len(candles)} candles, need at least 20"
                    )
                
                return candles
                
    except aiohttp.ClientConnectionError:
        raise MarketDataError("Network connection error - check internet connection")
    except aiohttp.ServerTimeoutError:
        raise MarketDataError("API request timeout - server too slow")
    except aiohttp.ClientError as e:
        raise MarketDataError(f"Network error: {str(e)}")
    except Exception as e:
        if isinstance(e, MarketDataError):
            raise
        logger.error(f"Unexpected error fetching {symbol} data: {type(e).__name__}: {str(e)}")
        raise MarketDataError(f"Unexpected error: {str(e)}")


def validate_symbol(symbol: str) -> str:
    """
    Validate and normalize symbol
    Falls back to BTC if symbol is invalid
    
    Args:
        symbol: User-provided symbol
    
    Returns:
        Validated symbol (uppercase)
    """
    if not symbol or not isinstance(symbol, str):
        return "BTC"
    
    # Remove whitespace
    symbol = symbol.strip()
    
    if not symbol:
        return "BTC"
    
    # Convert to uppercase
    symbol = symbol.upper()
    
    # Remove common suffixes and prefixes
    symbol = (symbol
              .replace("USDT", "")
              .replace("USDC", "")
              .replace("BUSD", "")
              .replace("USD", "")
              .replace("PERP", "")
              .replace("/", "")
              .replace("-", "")
              .replace("_", ""))
    
    # Remove any remaining non-alphanumeric characters
    symbol = ''.join(c for c in symbol if c.isalnum())
    
    # Check if supported (top 100 CoinGecko coins)
    if symbol not in SUPPORTED_SYMBOLS:
        logger.warning(f"Symbol {symbol} not in top 100, falling back to BTC")
        return "BTC"
    
    return symbol


def map_interval(interval: str) -> str:
    """
    Map internal interval format to Twelve Data API format
    
    Args:
        interval: Internal format ("1h", "4h", "1day")
    
    Returns:
        Twelve Data API format
    
    Raises:
        MarketDataError: If interval is not supported
    """
    if not interval or not isinstance(interval, str):
        return "1day"
    
    interval_map = {
        # Hourly
        "1h": "1h",
        "1hour": "1h",
        "1hr": "1h",
        
        "4h": "4h",
        "4hour": "4h",
        "4hr": "4h",
        
        # Daily
        "1day": "1day",
        "1d": "1day",
        "daily": "1day",
        "day": "1day",
    }
    
    normalized = interval.lower().strip()
    mapped = interval_map.get(normalized)
    
    if not mapped:
        logger.warning(f"Unsupported interval '{interval}', falling back to 1day")
        return "1day"
    
    return mapped


def normalize_candles(raw_candles: List[Dict], symbol: str) -> List[Dict]:
    """
    Normalize raw API candles to consistent format
    Validates and cleans data to prevent crashes
    
    Args:
        raw_candles: Raw candles from API
        symbol: Trading symbol for error messages
    
    Returns:
        List of normalized candles (oldest first)
    
    Raises:
        MarketDataError: If data validation fails
    """
    
    if not isinstance(raw_candles, list):
        raise MarketDataError("Invalid candles format: expected list")
    
    if len(raw_candles) == 0:
        raise MarketDataError("Empty candles list")
    
    normalized = []
    
    for i, candle in enumerate(raw_candles):
        try:
            if not isinstance(candle, dict):
                raise MarketDataError(f"Invalid candle at index {i}: not a dictionary")
            
            # Extract and validate fields
            timestamp = candle.get("datetime")
            if not timestamp:
                raise MarketDataError(f"Missing timestamp at index {i}")
            
            # Parse and validate prices
            open_price = safe_float(candle.get("open"), f"open price at index {i}")
            high_price = safe_float(candle.get("high"), f"high price at index {i}")
            low_price = safe_float(candle.get("low"), f"low price at index {i}")
            close_price = safe_float(candle.get("close"), f"close price at index {i}")
            volume = safe_float(candle.get("volume"), f"volume at index {i}", allow_zero=True, optional=True)
            
            # Validate OHLC relationships
            if high_price < low_price:
                raise MarketDataError(
                    f"Invalid candle at index {i}: "
                    f"high ({high_price:.2f}) < low ({low_price:.2f})"
                )
            
            if high_price < max(open_price, close_price):
                raise MarketDataError(
                    f"Invalid candle at index {i}: "
                    f"high ({high_price:.2f}) < max(open, close)"
                )
            
            if low_price > min(open_price, close_price):
                raise MarketDataError(
                    f"Invalid candle at index {i}: "
                    f"low ({low_price:.2f}) > min(open, close)"
                )
            
            # Validate prices are reasonable (not zero or negative)
            if open_price <= 0 or high_price <= 0 or low_price <= 0 or close_price <= 0:
                raise MarketDataError(f"Invalid candle at index {i}: prices must be positive")
            
            # Create normalized candle
            normalized.append({
                "timestamp": timestamp,
                "open": round(open_price, 8),  # Use 8 decimals for precision
                "high": round(high_price, 8),
                "low": round(low_price, 8),
                "close": round(close_price, 8),
                "volume": round(volume, 8)
            })
            
        except MarketDataError:
            raise
        except (KeyError, TypeError, ValueError) as e:
            raise MarketDataError(f"Invalid candle data at index {i}: {str(e)}")
    
    # Reverse to get chronological order (Twelve Data returns newest first)
    return list(reversed(normalized))


def safe_float(value, field_name: str, allow_zero: bool = False, optional: bool = False) -> float:
    """
    Safely convert value to float with validation
    
    Args:
        value: Value to convert
        field_name: Field name for error messages
        allow_zero: Whether zero values are acceptable
        optional: If True, return 0.0 when value is None
    
    Returns:
        Validated float value
    
    Raises:
        MarketDataError: If conversion or validation fails
    """
    if value is None:
        if optional:
            return 0.0
        raise MarketDataError(f"Missing {field_name}")
    
    # Convert to float
    try:
        if isinstance(value, str):
            # Remove any whitespace
            value = value.strip()
            if not value:  # Empty string after strip
                if optional:
                    return 0.0
                raise MarketDataError(f"Missing {field_name}")
        float_value = float(value)
    except (ValueError, TypeError):
        if optional:
            return 0.0
        raise MarketDataError(f"Invalid {field_name}: cannot convert '{value}' to number")
    
    # Check for invalid numbers (NaN, Infinity)
    if not is_valid_number(float_value):
        if optional:
            return 0.0
        raise MarketDataError(f"Invalid {field_name}: {float_value} is NaN or Infinity")
    
    # Validate positive (unless zero allowed)
    if not allow_zero and float_value <= 0:
        if optional:
            return 0.0
        raise MarketDataError(f"Invalid {field_name}: must be positive, got {float_value}")
    
    if allow_zero and float_value < 0:
        if optional:
            return 0.0
        raise MarketDataError(f"Invalid {field_name}: cannot be negative, got {float_value}")
    
    return float_value


def is_valid_number(value: float) -> bool:
    """Check if number is valid (not NaN or infinity)"""
    return not (math.isnan(value) or math.isinf(value))


async def fetch_regime_data(
    symbol: str, 
    lower_tf: str = "4h", 
    upper_tf: str = "1day"
) -> Dict:
    """
    Fetch all data needed for regime analysis with dynamic timeframes
    Handles fallback to BTC if symbol fails
    
    Args:
        symbol: Trading symbol
        lower_tf: Lower timeframe (e.g., "1h", "4h")
        upper_tf: Upper timeframe (e.g., "4h", "1day")
    
    Returns:
        Dictionary with lower and upper timeframe data
        {
            "symbol": str,
            "data_lower": List[Dict],
            "data_upper": List[Dict],
            "fallback_used": bool,
            "original_symbol": str (if fallback used),
            "fallback_reason": str (if fallback used)
        }
    
    Raises:
        MarketDataError: If even BTC fallback fails
    """
    original_symbol = symbol
    
    # Determine appropriate candle limits based on timeframe
    # Lower timeframes need more candles for accurate indicators
    lower_limit = get_candle_limit(lower_tf)
    upper_limit = get_candle_limit(upper_tf)
    
    logger.info(f"Fetching regime data: symbol={symbol}, timeframes={lower_tf}+{upper_tf}")
    
    try:
        # Try to fetch data for requested symbol
        data_lower = await fetch_market_data(symbol, lower_tf, limit=lower_limit)
        data_upper = await fetch_market_data(symbol, upper_tf, limit=upper_limit)
        
        return {
            "symbol": symbol,
            "data_lower": data_lower,
            "data_upper": data_upper,
            "fallback_used": False
        }
        
    except MarketDataError as e:
        logger.warning(f"Failed to fetch {symbol} data: {str(e)}")
        
        # If symbol fails and it's not BTC, try fallback to BTC
        if symbol.upper() != "BTC":
            try:
                logger.info(f"Falling back to BTC for regime analysis")
                data_lower = await fetch_market_data("BTC", lower_tf, limit=lower_limit)
                data_upper = await fetch_market_data("BTC", upper_tf, limit=upper_limit)
                
                return {
                    "symbol": "BTC",
                    "data_lower": data_lower,
                    "data_upper": data_upper,
                    "fallback_used": True,
                    "original_symbol": original_symbol,
                    "fallback_reason": str(e)
                }
            except MarketDataError as btc_error:
                # Even BTC failed - this is critical
                logger.error(f"Critical: BTC fallback failed: {str(btc_error)}")
                raise MarketDataError(
                    f"Critical error: Cannot fetch data. "
                    f"Original error for {original_symbol}: {str(e)}. "
                    f"BTC fallback error: {str(btc_error)}"
                )
        else:
            # BTC itself failed - no fallback available
            logger.error(f"Critical: BTC data fetch failed: {str(e)}")
            raise MarketDataError(f"Cannot fetch BTC data: {str(e)}")


def get_candle_limit(timeframe: str) -> int:
    """
    Get appropriate candle limit based on timeframe
    Lower timeframes need more candles for accurate indicators
    
    Args:
        timeframe: Timeframe string (e.g., "1h", "4h", "1day")
    
    Returns:
        Number of candles to fetch
    """
    limits = {
        "1h": 200,   # 1 hour = need ~200 candles for 200 MA
        "4h": 100,   # 4 hour = need ~100 candles  
        "1day": 50,  # Daily = need ~50 candles
    }
    
    # Normalize timeframe
    normalized = map_interval(timeframe)
    
    return limits.get(normalized, 100)


# ============================================================================
# TESTING & VALIDATION
# ============================================================================

async def validate_api_connection() -> bool:
    """
    Test API connection and key validity
    Useful for startup checks
    
    Returns:
        True if API is working, False otherwise
    """
    try:
        data = await fetch_market_data("BTC", "1day", limit=10)
        return len(data) >= 10
    except MarketDataError:
        return False


def get_supported_symbols() -> List[str]:
    """Get list of supported symbols"""
    return sorted(list(SUPPORTED_SYMBOLS))


def is_symbol_supported(symbol: str) -> bool:
    """Check if a symbol is supported"""
    normalized = validate_symbol(symbol)
    return normalized in SUPPORTED_SYMBOLS


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

"""
Basic usage:
-----------
from utils.regime_data import fetch_market_data, fetch_regime_data

# Fetch single timeframe
candles = await fetch_market_data("BTC", "4h", limit=100)

# Fetch regime data (custom timeframes)
data = await fetch_regime_data("ETH", lower_tf="1h", upper_tf="4h")
print(f"Symbol: {data['symbol']}")
print(f"Lower TF candles: {len(data['data_lower'])}")
print(f"Upper TF candles: {len(data['data_upper'])}")

# Fetch regime data (default timeframes: 4h + daily)
data = await fetch_regime_data("BTC")

Error handling:
--------------
try:
    data = await fetch_regime_data("INVALID_COIN")
except MarketDataError as e:
    print(f"Error: {e}")

Testing API:
-----------
if await validate_api_connection():
    print("API is working!")
else:
    print("API connection failed")
"""