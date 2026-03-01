# ----------------------------------------------------------------------------
# utils/regime_data.py - Extended Timeframe Support
# ----------------------------------------------------------------------------
"""
Fetch and validate market data from Twelve Data API
Supports TOP 10 most used timeframes for comprehensive analysis
Handles errors, validates data, and normalizes output
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

# ============================================================================
# TOP 10 TIMEFRAMES CONFIGURATION
# ============================================================================

# Professional timeframe hierarchy (most used in trading)
SUPPORTED_TIMEFRAMES = {
    # Scalping / Day Trading
    "1m": {"api": "1min", "limit": 300, "name": "1 Minute"},
    "5m": {"api": "5min", "limit": 250, "name": "5 Minutes"},
    "15m": {"api": "15min", "limit": 220, "name": "15 Minutes"},
    "30m": {"api": "30min", "limit": 200, "name": "30 Minutes"},
    
    # Intraday / Swing Trading
    "1h": {"api": "1h", "limit": 200, "name": "1 Hour"},
    "2h": {"api": "2h", "limit": 150, "name": "2 Hours"},
    "4h": {"api": "4h", "limit": 150, "name": "4 Hours"},
    
    # Position Trading
    "8h": {"api": "8h", "limit": 100, "name": "8 Hours"},
    "1d": {"api": "1day", "limit": 100, "name": "Daily"},
    "1w": {"api": "1week", "limit": 80, "name": "Weekly"}
}

# Aliases for user convenience
TIMEFRAME_ALIASES = {
    # Minute aliases
    "1min": "1m",
    "5min": "5m",
    "15min": "15m",
    "30min": "30m",
    
    # Hour aliases
    "1hour": "1h",
    "1hr": "1h",
    "2hour": "2h",
    "2hr": "2h",
    "4hour": "4h",
    "4hr": "4h",
    "8hour": "8h",
    "8hr": "8h",
    
    # Day aliases
    "1day": "1d",
    "daily": "1d",
    "day": "1d",
    "d": "1d",
    
    # Week aliases
    "1week": "1w",
    "weekly": "1w",
    "week": "1w",
    "w": "1w"
}


def get_supported_timeframe_list() -> List[str]:
    """Get list of supported timeframes with names"""
    return [
        f"{tf} ({config['name']})" 
        for tf, config in SUPPORTED_TIMEFRAMES.items()
    ]


def validate_timeframe(timeframe: str) -> str:
    """
    Validate and normalize timeframe
    
    Args:
        timeframe: User-provided timeframe
    
    Returns:
        Normalized timeframe (e.g., "1h", "4h", "1d")
    
    Raises:
        MarketDataError: If timeframe is not supported
    """
    if not timeframe or not isinstance(timeframe, str):
        return "4h"  # Default to 4h
    
    # Normalize
    normalized = timeframe.lower().strip()
    
    # Check aliases first
    if normalized in TIMEFRAME_ALIASES:
        normalized = TIMEFRAME_ALIASES[normalized]
    
    # Check if supported
    if normalized not in SUPPORTED_TIMEFRAMES:
        supported = ', '.join(SUPPORTED_TIMEFRAMES.keys())
        raise MarketDataError(
            f"Timeframe '{timeframe}' not supported. "
            f"Supported: {supported}"
        )
    
    return normalized


def get_timeframe_config(timeframe: str) -> Dict:
    """
    Get configuration for a timeframe
    
    Args:
        timeframe: Normalized timeframe (e.g., "1h")
    
    Returns:
        Configuration dict with api, limit, name
    """
    validated = validate_timeframe(timeframe)
    return SUPPORTED_TIMEFRAMES[validated]


# ============================================================================
# SYMBOL VALIDATION (TOP 100 COINGECKO)
# ============================================================================

def load_supported_symbols() -> set:
    """Load supported symbols from top100_coingecko_ids.json"""
    try:
        with open("services/top100_coingecko_ids.json", "r") as f:
            data = json.load(f)

            if not isinstance(data, dict):
                raise ValueError("top100_coingecko_ids.json must be a dict")

            symbols = {symbol.upper() for symbol in data.keys()}
            logger.info(f"Loaded {len(symbols)} supported symbols")
            return symbols

    except Exception as e:
        logger.error(f"Error loading symbols: {e}")
        return {
            "BTC", "ETH", "BNB", "XRP", "ADA", "DOGE", "SOL", "MATIC",
            "DOT", "AVAX", "LINK", "UNI", "ATOM", "LTC", "ETC"
        }


SUPPORTED_SYMBOLS = load_supported_symbols()


class MarketDataError(Exception):
    """Custom exception for market data errors"""
    pass


def validate_symbol(symbol: str) -> str:
    """
    Validate and normalize symbol
    
    Args:
        symbol: User-provided symbol
    
    Returns:
        Validated symbol (uppercase)
    """
    if not symbol or not isinstance(symbol, str):
        return "BTC"
    
    symbol = symbol.strip().upper()
    
    if not symbol:
        return "BTC"
    
    # Remove common suffixes
    symbol = (symbol
              .replace("USDT", "")
              .replace("USDC", "")
              .replace("BUSD", "")
              .replace("USD", "")
              .replace("PERP", "")
              .replace("/", "")
              .replace("-", "")
              .replace("_", ""))
    
    symbol = ''.join(c for c in symbol if c.isalnum())
    
    if symbol not in SUPPORTED_SYMBOLS:
        logger.warning(f"Symbol {symbol} not in top 100, falling back to BTC")
        return "BTC"
    
    return symbol


# ============================================================================
# MARKET DATA FETCHING
# ============================================================================

async def fetch_market_data(
    symbol: str, 
    interval: str, 
    limit: int = None
) -> List[Dict]:
    """
    Fetch OHLCV data from Twelve Data API with validation
    
    Args:
        symbol: Trading pair (e.g., "BTC", "ETH")
        interval: Timeframe (e.g., "1m", "5m", "15m", "1h", "4h", "1d", "1w")
        limit: Number of candles (auto-determined if None)
    
    Returns:
        List of normalized candles with OHLCV data (oldest first)
    
    Raises:
        MarketDataError: If data fetch fails or validation fails
    """
    
    # Validate inputs
    validated_symbol = validate_symbol(symbol)
    validated_timeframe = validate_timeframe(interval)
    
    # Get timeframe config
    tf_config = get_timeframe_config(validated_timeframe)
    
    # Use provided limit or default from config
    if limit is None:
        limit = tf_config["limit"]
    
    # Convert symbol format for Twelve Data
    api_symbol = f"{validated_symbol}/USD"
    api_interval = tf_config["api"]
    
    # Validate API key
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
    
    logger.info(
        f"Fetching {symbol} data: timeframe={validated_timeframe} "
        f"({tf_config['name']}), limit={limit}"
    )
    
    try:
        timeout = aiohttp.ClientTimeout(total=15, connect=5)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as response:
                
                # Handle HTTP errors
                if response.status == 400:
                    raise MarketDataError(f"Invalid request for {validated_symbol}")
                elif response.status == 401:
                    raise MarketDataError("Invalid API key")
                elif response.status == 403:
                    raise MarketDataError("API access forbidden")
                elif response.status == 404:
                    raise MarketDataError(f"Symbol {validated_symbol} not found")
                elif response.status == 429:
                    raise MarketDataError("API rate limit exceeded")
                elif response.status >= 500:
                    raise MarketDataError("Twelve Data API server error")
                elif response.status != 200:
                    raise MarketDataError(f"API error: HTTP {response.status}")
                
                # Parse JSON
                try:
                    data = await response.json()
                except aiohttp.ContentTypeError:
                    raise MarketDataError("Invalid API response format")
                
                # Check for API errors
                if isinstance(data, dict):
                    if "status" in data and data["status"] == "error":
                        error_msg = data.get("message", "Unknown API error")
                        raise MarketDataError(f"API error: {error_msg}")
                    
                    if "code" in data and data["code"] != 200:
                        error_msg = data.get("message", "Unknown API error")
                        raise MarketDataError(f"API error: {error_msg}")
                
                # Validate structure
                if not isinstance(data, dict) or "values" not in data:
                    raise MarketDataError("Invalid API response structure")
                
                if not data["values"] or not isinstance(data["values"], list):
                    raise MarketDataError(f"No data available for {validated_symbol}")
                
                # Normalize candles
                candles = normalize_candles(data["values"], validated_symbol)
                
                logger.info(
                    f"✅ Fetched {len(candles)} candles for {symbol} "
                    f"({validated_timeframe})"
                )
                
                # Minimum data validation
                if len(candles) < 20:
                    raise MarketDataError(
                        f"Insufficient data for {validated_symbol}: "
                        f"got {len(candles)} candles, need at least 20"
                    )
                
                return candles
                
    except aiohttp.ClientConnectionError:
        raise MarketDataError("Network connection error")
    except aiohttp.ServerTimeoutError:
        raise MarketDataError("API request timeout")
    except aiohttp.ClientError as e:
        raise MarketDataError(f"Network error: {str(e)}")
    except Exception as e:
        if isinstance(e, MarketDataError):
            raise
        logger.error(f"Unexpected error: {type(e).__name__}: {str(e)}")
        raise MarketDataError(f"Unexpected error: {str(e)}")


def normalize_candles(raw_candles: List[Dict], symbol: str) -> List[Dict]:
    """
    Normalize raw API candles to consistent format
    
    Args:
        raw_candles: Raw candles from API
        symbol: Trading symbol
    
    Returns:
        List of normalized candles (oldest first)
    """
    if not isinstance(raw_candles, list) or len(raw_candles) == 0:
        raise MarketDataError("Invalid or empty candles data")
    
    normalized = []
    
    for i, candle in enumerate(raw_candles):
        try:
            if not isinstance(candle, dict):
                raise MarketDataError(f"Invalid candle at index {i}")
            
            timestamp = candle.get("datetime")
            if not timestamp:
                raise MarketDataError(f"Missing timestamp at index {i}")
            
            # Parse prices
            open_price = safe_float(candle.get("open"), f"open at {i}")
            high_price = safe_float(candle.get("high"), f"high at {i}")
            low_price = safe_float(candle.get("low"), f"low at {i}")
            close_price = safe_float(candle.get("close"), f"close at {i}")
            volume = safe_float(candle.get("volume"), f"volume at {i}", optional=True)
            
            # Validate OHLC relationships
            if high_price < low_price:
                raise MarketDataError(f"Invalid OHLC at {i}: high < low")
            
            if high_price < max(open_price, close_price):
                raise MarketDataError(f"Invalid OHLC at {i}: high < max(O,C)")
            
            if low_price > min(open_price, close_price):
                raise MarketDataError(f"Invalid OHLC at {i}: low > min(O,C)")
            
            if any(p <= 0 for p in [open_price, high_price, low_price, close_price]):
                raise MarketDataError(f"Invalid prices at {i}: must be positive")
            
            normalized.append({
                "timestamp": timestamp,
                "open": round(open_price, 8),
                "high": round(high_price, 8),
                "low": round(low_price, 8),
                "close": round(close_price, 8),
                "volume": round(volume, 8)
            })
            
        except MarketDataError:
            raise
        except Exception as e:
            raise MarketDataError(f"Invalid candle at {i}: {str(e)}")
    
    # Reverse to chronological order (Twelve Data returns newest first)
    return list(reversed(normalized))


def safe_float(value, field_name: str, optional: bool = False) -> float:
    """Safely convert value to float"""
    if value is None:
        if optional:
            return 0.0
        raise MarketDataError(f"Missing {field_name}")
    
    try:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                if optional:
                    return 0.0
                raise MarketDataError(f"Empty {field_name}")
        
        float_value = float(value)
    except (ValueError, TypeError):
        if optional:
            return 0.0
        raise MarketDataError(f"Invalid {field_name}: cannot convert to number")
    
    if not is_valid_number(float_value):
        if optional:
            return 0.0
        raise MarketDataError(f"Invalid {field_name}: NaN or Infinity")
    
    return float_value


def is_valid_number(value: float) -> bool:
    """Check if number is valid"""
    return not (math.isnan(value) or math.isinf(value))


# ============================================================================
# REGIME DATA FETCHING (MULTI-TIMEFRAME)
# ============================================================================

async def fetch_regime_data(
    symbol: str, 
    lower_tf: str = "4h", 
    upper_tf: str = "1d"
) -> Dict:
    """
    Fetch regime data with two timeframes for comprehensive analysis
    
    Args:
        symbol: Trading symbol (e.g., "BTC", "ETH")
        lower_tf: Lower timeframe (e.g., "1h", "4h")
        upper_tf: Upper timeframe (e.g., "1d", "1w")
    
    Returns:
        Dict with data from both timeframes
    """
    original_symbol = symbol
    
    # Validate timeframes
    lower_validated = validate_timeframe(lower_tf)
    upper_validated = validate_timeframe(upper_tf)
    
    logger.info(
        f"Fetching regime data: symbol={symbol}, "
        f"timeframes={lower_validated}+{upper_validated}"
    )
    
    try:
        # Fetch both timeframes
        data_lower = await fetch_market_data(symbol, lower_validated)
        data_upper = await fetch_market_data(symbol, upper_validated)
        
        return {
            "symbol": symbol,
            "data_lower": data_lower,
            "data_upper": data_upper,
            "timeframe_lower": lower_validated,
            "timeframe_upper": upper_validated,
            "fallback_used": False
        }
        
    except MarketDataError as e:
        logger.warning(f"Failed to fetch {symbol} data: {str(e)}")
        
        # Fallback to BTC if not already BTC
        if symbol.upper() != "BTC":
            try:
                logger.info("Falling back to BTC")
                data_lower = await fetch_market_data("BTC", lower_validated)
                data_upper = await fetch_market_data("BTC", upper_validated)
                
                return {
                    "symbol": "BTC",
                    "data_lower": data_lower,
                    "data_upper": data_upper,
                    "timeframe_lower": lower_validated,
                    "timeframe_upper": upper_validated,
                    "fallback_used": True,
                    "original_symbol": original_symbol,
                    "fallback_reason": str(e)
                }
            except MarketDataError as btc_error:
                logger.error(f"BTC fallback failed: {str(btc_error)}")
                raise MarketDataError(
                    f"Critical error: {str(e)}. BTC fallback: {str(btc_error)}"
                )
        else:
            logger.error(f"BTC data fetch failed: {str(e)}")
            raise MarketDataError(f"Cannot fetch BTC data: {str(e)}")


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

async def validate_api_connection() -> bool:
    """Test API connection"""
    try:
        data = await fetch_market_data("BTC", "1d", limit=10)
        return len(data) >= 10
    except MarketDataError:
        return False


def get_supported_symbols() -> List[str]:
    """Get list of supported symbols"""
    return sorted(list(SUPPORTED_SYMBOLS))


def is_symbol_supported(symbol: str) -> bool:
    """Check if symbol is supported"""
    normalized = validate_symbol(symbol)
    return normalized in SUPPORTED_SYMBOLS


def is_timeframe_supported(timeframe: str) -> bool:
    """Check if timeframe is supported"""
    try:
        validate_timeframe(timeframe)
        return True
    except MarketDataError:
        return False


def get_timeframe_info(timeframe: str) -> Dict:
    """
    Get information about a timeframe
    
    Returns:
        Dict with name, api format, and recommended limit
    """
    try:
        validated = validate_timeframe(timeframe)
        config = SUPPORTED_TIMEFRAMES[validated]
        return {
            "timeframe": validated,
            "name": config["name"],
            "api_format": config["api"],
            "recommended_limit": config["limit"]
        }
    except MarketDataError as e:
        return {"error": str(e)}


