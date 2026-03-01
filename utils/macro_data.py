# ============================================================================
# MACRO DATA SYSTEM - STANDALONE (FIXED & HARDENED)
# ============================================================================
"""
Standalone data fetcher for macro assets.

Supports:
- Crypto (BTC/USD, ETH/USD)
- Metals (XAU/USD, XAG/USD)
- Indices (DXY, SPX)

Key design rules:
- Volume is OPTIONAL (never required for macro assets)
- OHLC must be valid and positive
- No assumptions about exchange-style candles
"""

import aiohttp
import os
import math
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY")
BASE_URL = "https://api.twelvedata.com/time_series"


# ----------------------------------------------------------------------------
# Exceptions
# ----------------------------------------------------------------------------
class MacroDataError(Exception):
    """Raised when macro data cannot be fetched or validated"""
    pass


# ----------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------
async def fetch_macro_asset(
    symbol: str,
    interval: str = "1day",
    limit: int = 2
) -> List[Dict]:
    """
    Fetch and normalize OHLC data for a macro asset.

    Returns candles ordered oldest → newest.

    NOTE:
    - Volume is optional and may be None
    - Only OHLC is required for macro analysis
    """

    if not TWELVE_DATA_API_KEY:
        raise MacroDataError("TWELVE_DATA_API_KEY is not set")

    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": limit,
        "apikey": TWELVE_DATA_API_KEY,
        "format": "JSON",
    }

    timeout = aiohttp.ClientTimeout(total=10, connect=5)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(BASE_URL, params=params) as response:

                if response.status != 200:
                    raise MacroDataError(f"HTTP {response.status} for {symbol}")

                try:
                    payload = await response.json()
                except Exception:
                    raise MacroDataError("Invalid JSON response from API")

    except aiohttp.ClientError as e:
        raise MacroDataError(f"Network error: {str(e)}")

    # ------------------------------------------------------------------
    # API-level errors
    # ------------------------------------------------------------------
    if isinstance(payload, dict) and payload.get("status") == "error":
        raise MacroDataError(payload.get("message", "API error"))

    values = payload.get("values")
    if not isinstance(values, list) or not values:
        raise MacroDataError(f"No candle data returned for {symbol}")

    candles = _normalize_candles(values, symbol)

    if not candles:
        raise MacroDataError(f"No valid candles after normalization for {symbol}")

    logger.info(f"Fetched {len(candles)} macro candles for {symbol}")
    return candles


# ----------------------------------------------------------------------------
# Normalization
# ----------------------------------------------------------------------------
def _normalize_candles(raw: List[Dict], symbol: str) -> List[Dict]:
    """
    Normalize Twelve Data candles.

    Output format:
    {
        timestamp: str,
        open: float,
        high: float,
        low: float,
        close: float,
        volume: Optional[float]
    }
    """

    normalized: List[Dict] = []

    for idx, candle in enumerate(raw):
        if not isinstance(candle, dict):
            logger.warning(f"{symbol}: skipping invalid candle at {idx}")
            continue

        try:
            ts = candle.get("datetime")
            if not ts:
                raise MacroDataError("Missing timestamp")

            open_p = _positive_float(candle.get("open"), "open")
            high_p = _positive_float(candle.get("high"), "high")
            low_p = _positive_float(candle.get("low"), "low")
            close_p = _positive_float(candle.get("close"), "close")

            # OHLC integrity checks
            if high_p < max(open_p, close_p):
                raise MacroDataError("High < open/close")
            if low_p > min(open_p, close_p):
                raise MacroDataError("Low > open/close")

            # Volume is OPTIONAL for macro assets
            volume = _optional_float(candle.get("volume"))

            normalized.append({
                "timestamp": ts,
                "open": round(open_p, 8),
                "high": round(high_p, 8),
                "low": round(low_p, 8),
                "close": round(close_p, 8),
                "volume": volume
            })

        except MacroDataError as e:
            logger.warning(f"{symbol}: candle {idx} skipped ({e})")
            continue

    # Twelve Data returns newest first → reverse
    return list(reversed(normalized))


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def _positive_float(value, name: str) -> float:
    """Convert to float and require > 0"""
    try:
        val = float(value)
    except (TypeError, ValueError):
        raise MacroDataError(f"Invalid {name}")

    if math.isnan(val) or math.isinf(val) or val <= 0:
        raise MacroDataError(f"Invalid {name}")

    return val


def _optional_float(value) -> Optional[float]:
    """
    Convert volume safely.
    Returns None if missing, zero, invalid, or not provided.
    """
    if value in (None, "", 0, "0"):
        return None

    try:
        val = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(val) or math.isinf(val) or val < 0:
        return None

    return round(val, 8)