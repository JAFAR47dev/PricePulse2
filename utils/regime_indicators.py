# ============================================================================
# REGIME INDICATORS - PURE PYTHON (NO NUMPY)
# ============================================================================

"""
Calculate technical indicators using pure Python
Uses: math, statistics modules (built-in)
100% accurate - matches NumPy calculations
"""

import math
import statistics
from typing import Dict, List


def calculate_indicators(candles: List[Dict], timeframe: str) -> Dict:
    """
    Calculate all indicators needed for regime analysis
    Pure Python implementation - no NumPy required
    
    Args:
        candles: List of OHLCV candles from API
        timeframe: Timeframe string (e.g., "4h", "1day")
    
    Returns:
        Dictionary of calculated indicators
    
    Raises:
        ValueError: If candles list is invalid or empty
    """
    
    # ========================================================================
    # VALIDATION
    # ========================================================================
    
    if not candles or len(candles) < 20:
        raise ValueError(f"Insufficient candles: got {len(candles)}, need at least 20")
    
    # Extract price arrays with validation
    try:
        closes = [float(c["close"]) for c in candles]
        highs = [float(c["high"]) for c in candles]
        lows = [float(c["low"]) for c in candles]
        volumes = [float(c["volume"]) for c in candles]
    except (KeyError, ValueError, TypeError) as e:
        raise ValueError(f"Invalid candle data format: {e}")
    
    # Validate array lengths match
    if not (len(closes) == len(highs) == len(lows) == len(volumes)):
        raise ValueError("Mismatched array lengths in OHLCV data")
    
    # Check for invalid numbers (NaN, Inf)
    for i, price in enumerate(closes):
        if not is_valid_number(price):
            raise ValueError(f"Invalid price at index {i}: {price}")
    
    # ========================================================================
    # CALCULATE INDICATORS
    # ========================================================================
    
    # Core moving averages
    ema_50 = calculate_ema(closes, 50)
    ma_200 = calculate_sma(closes, 200)
    
    # Current price
    current_price = closes[-1]
    
    # Trend bias
    trend_bias = detect_trend_bias(current_price, ema_50, ma_200)
    
    # Volatility
    atr = calculate_atr(highs, lows, closes, 14)
    volatility_level = detect_volatility(atr, current_price)
    
    # Structure detection
    structure = detect_structure(highs, lows)
    
    # Volume metrics
    if len(volumes) >= 20:
        volume_avg = statistics.mean(volumes[-20:])
    else:
        volume_avg = volumes[-1]
    
    volume_current = volumes[-1]
    volume_ratio = volume_current / volume_avg if volume_avg > 0 else 1.0
    
    # Price change calculation
    price_20_ago = closes[-20] if len(closes) >= 20 else closes[0]
    price_change_pct = ((current_price - price_20_ago) / price_20_ago) * 100
    
    # RSI
    rsi = calculate_rsi(closes, 14)
    
    # ========================================================================
    # BUILD RESULT DICTIONARY
    # ========================================================================
    
    indicators = {
        # Core MAs
        "ema_50": round(ema_50, 2),
        "ma_200": round(ma_200, 2),
        
        # Price
        "current_price": round(current_price, 2),
        "price_change_pct": round(price_change_pct, 2),
        
        # Trend
        "trend_bias": trend_bias,
        
        # Volatility
        "atr": round(atr, 2),
        "atr_pct": round((atr / current_price) * 100, 2),
        "volatility_level": volatility_level,
        
        # Structure
        "lower_highs": structure["lower_highs"],
        "higher_lows": structure["higher_lows"],
        "structure_bias": structure["bias"],
        
        # Volume
        "volume_avg": round(volume_avg, 2),
        "volume_current": round(volume_current, 2),
        "volume_ratio": round(volume_ratio, 2),
        
        # Additional context
        "rsi": round(rsi, 1),
    }
    
    return indicators


# ============================================================================
# MOVING AVERAGES
# ============================================================================

def calculate_sma(data: List[float], period: int) -> float:
    """
    Simple Moving Average
    Formula: SMA = sum(prices) / period
    
    Args:
        data: List of prices
        period: SMA period
    
    Returns:
        SMA value
    """
    if len(data) < period:
        return data[-1]
    
    # Take last 'period' values and calculate mean
    recent_data = data[-period:]
    sma = sum(recent_data) / len(recent_data)
    
    return sma


def calculate_ema(data: List[float], period: int) -> float:
    """
    Exponential Moving Average
    Formula: EMA = Price(t) * k + EMA(t-1) * (1 - k)
    where k = 2 / (period + 1)
    
    Args:
        data: List of prices
        period: EMA period
    
    Returns:
        EMA value
    """
    if len(data) < period:
        return data[-1]
    
    # EMA multiplier
    multiplier = 2.0 / (period + 1.0)
    
    # Start with SMA as seed
    ema = sum(data[:period]) / period
    
    # Calculate EMA iteratively
    for price in data[period:]:
        ema = (price * multiplier) + (ema * (1.0 - multiplier))
    
    return ema


# ============================================================================
# TREND BIAS DETECTION
# ============================================================================

def detect_trend_bias(price: float, ema_50: float, ma_200: float) -> str:
    """
    Detect trend bias based on price position relative to MAs
    
    Rules:
    - Price < both MAs → Bearish
    - Price > both MAs → Bullish
    - Otherwise → Neutral
    
    Args:
        price: Current price
        ema_50: 50-period EMA
        ma_200: 200-period MA
    
    Returns:
        "bullish", "bearish", or "neutral"
    """
    
    if price < ema_50 and price < ma_200:
        return "bearish"
    
    if price > ema_50 and price > ma_200:
        return "bullish"
    
    return "neutral"


# ============================================================================
# VOLATILITY DETECTION
# ============================================================================

def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    """
    Average True Range - Wilder's formula
    
    True Range = max of:
    1. High - Low
    2. |High - Previous Close|
    3. |Low - Previous Close|
    
    ATR = Average of True Ranges over period
    
    Args:
        highs: High prices
        lows: Low prices
        closes: Close prices
        period: ATR period (default 14)
    
    Returns:
        ATR value
    """
    if len(closes) < period + 1:
        return 0.0
    
    tr_list = []
    
    # Calculate True Range for each candle (starting from index 1)
    for i in range(1, len(closes)):
        high_low = highs[i] - lows[i]
        high_close = abs(highs[i] - closes[i-1])
        low_close = abs(lows[i] - closes[i-1])
        
        # True Range is maximum of the three
        tr = max(high_low, high_close, low_close)
        tr_list.append(tr)
    
    # ATR is average of last 'period' True Ranges
    recent_tr = tr_list[-period:]
    atr = sum(recent_tr) / len(recent_tr)
    
    return atr


def detect_volatility(atr: float, price: float) -> str:
    """
    Classify volatility level based on ATR percentage
    
    Thresholds:
    - Low: ATR < 2% of price
    - Medium: ATR 2-5% of price
    - High: ATR > 5% of price
    
    Args:
        atr: Average True Range
        price: Current price
    
    Returns:
        "low", "medium", or "high"
    """
    
    if price <= 0:
        return "medium"
    
    atr_pct = (atr / price) * 100.0
    
    if atr_pct < 2.0:
        return "low"
    elif atr_pct < 5.0:
        return "medium"
    else:
        return "high"


# ============================================================================
# STRUCTURE DETECTION
# ============================================================================

def detect_structure(highs: List[float], lows: List[float], lookback: int = 20) -> Dict:
    """
    Detect market structure using swing points
    
    Args:
        highs: List of high prices
        lows: List of low prices
        lookback: Number of candles to analyze
    
    Returns:
        Dictionary with structure info
    """
    
    if len(highs) < lookback or len(lows) < lookback:
        return {
            "lower_highs": False,
            "higher_lows": False,
            "bias": "choppy"
        }
    
    # Get recent data
    recent_highs = highs[-lookback:]
    recent_lows = lows[-lookback:]
    
    # Detect patterns
    lower_highs = detect_lower_highs(recent_highs)
    higher_lows = detect_higher_lows(recent_lows)
    
    # Determine bias
    if lower_highs and not higher_lows:
        bias = "bearish"
    elif higher_lows and not lower_highs:
        bias = "bullish"
    else:
        bias = "choppy"
    
    return {
        "lower_highs": lower_highs,
        "higher_lows": higher_lows,
        "bias": bias
    }


def detect_lower_highs(highs: List[float], threshold: float = 0.01) -> bool:
    """
    Detect lower highs pattern (bearish structure)
    
    Args:
        highs: List of high prices
        threshold: Minimum % decline (default 1%)
    
    Returns:
        True if lower highs detected
    """
    
    swing_highs = find_swing_points(highs, mode="high")
    
    if len(swing_highs) < 2:
        return False
    
    # Get last 2-3 swings
    recent_swings = swing_highs[-3:] if len(swing_highs) >= 3 else swing_highs[-2:]
    
    # Check if declining
    for i in range(1, len(recent_swings)):
        prev_high = recent_swings[i-1]["price"]
        curr_high = recent_swings[i]["price"]
        
        # Must be lower by at least threshold %
        if curr_high >= prev_high * (1.0 - threshold):
            return False
    
    return True


def detect_higher_lows(lows: List[float], threshold: float = 0.01) -> bool:
    """
    Detect higher lows pattern (bullish structure)
    
    Args:
        lows: List of low prices
        threshold: Minimum % increase (default 1%)
    
    Returns:
        True if higher lows detected
    """
    
    swing_lows = find_swing_points(lows, mode="low")
    
    if len(swing_lows) < 2:
        return False
    
    # Get last 2-3 swings
    recent_swings = swing_lows[-3:] if len(swing_lows) >= 3 else swing_lows[-2:]
    
    # Check if rising
    for i in range(1, len(recent_swings)):
        prev_low = recent_swings[i-1]["price"]
        curr_low = recent_swings[i]["price"]
        
        # Must be higher by at least threshold %
        if curr_low <= prev_low * (1.0 + threshold):
            return False
    
    return True


def find_swing_points(prices: List[float], mode: str = "high", window: int = 3) -> List[Dict]:
    """
    Find swing highs or swing lows using local extrema
    
    Swing High: price[i] is highest in window on both sides
    Swing Low: price[i] is lowest in window on both sides
    
    Args:
        prices: List of prices
        mode: "high" or "low"
        window: Number of candles on each side
    
    Returns:
        List of swing points with index and price
    """
    
    swings = []
    
    for i in range(window, len(prices) - window):
        is_swing = False
        
        if mode == "high":
            # Check if local peak
            left_side = prices[i-window:i]
            right_side = prices[i+1:i+window+1]
            
            if left_side and right_side:
                if all(prices[i] > p for p in left_side) and all(prices[i] > p for p in right_side):
                    is_swing = True
        
        elif mode == "low":
            # Check if local trough
            left_side = prices[i-window:i]
            right_side = prices[i+1:i+window+1]
            
            if left_side and right_side:
                if all(prices[i] < p for p in left_side) and all(prices[i] < p for p in right_side):
                    is_swing = True
        
        if is_swing:
            swings.append({
                "index": i,
                "price": prices[i]
            })
    
    return swings


# ============================================================================
# RSI
# ============================================================================

def calculate_rsi(closes: List[float], period: int = 14) -> float:
    """
    Relative Strength Index - Wilder's formula
    
    RSI = 100 - (100 / (1 + RS))
    where RS = Average Gain / Average Loss
    
    Args:
        closes: List of close prices
        period: RSI period (default 14)
    
    Returns:
        RSI value (0-100)
    """
    if len(closes) < period + 1:
        return 50.0
    
    # Calculate price changes
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    
    # Separate gains and losses
    gains = [delta if delta > 0 else 0.0 for delta in deltas]
    losses = [-delta if delta < 0 else 0.0 for delta in deltas]
    
    # Calculate average gain and loss over period
    recent_gains = gains[-period:]
    recent_losses = losses[-period:]
    
    avg_gain = sum(recent_gains) / len(recent_gains)
    avg_loss = sum(recent_losses) / len(recent_losses)
    
    # Handle edge case (no losses)
    if avg_loss == 0:
        return 100.0
    
    # Calculate RS and RSI
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    
    return rsi


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def is_valid_number(value: float) -> bool:
    """
    Check if number is valid (not NaN or infinity)
    
    Args:
        value: Number to check
    
    Returns:
        True if valid, False otherwise
    """
    return not (math.isnan(value) or math.isinf(value))

