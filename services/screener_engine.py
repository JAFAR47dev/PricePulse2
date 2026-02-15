# services/screener_engine.py
import asyncio
import json
import os
import time
from typing import Dict, Any, List, Tuple, Optional

from services.screener_data import load_screener_data, is_bullish_engulfing

# Load top 100 coin IDs (symbol -> id)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COINGECKO_IDS_PATH = os.path.join(BASE_DIR, "services", "top100_coingecko_ids.json")

try:
    with open(COINGECKO_IDS_PATH, "r") as f:
        TOP_100_COINS = json.load(f)
    COINS_LIST = [{"symbol": symbol.upper(), "id": cid} for symbol, cid in TOP_100_COINS.items()]
except (FileNotFoundError, json.JSONDecodeError) as e:
    print(f"[screener] Error loading coin list: {e}")
    COINS_LIST = []

# Rate limiting: 20 coins per minute = 1 coin every 3 seconds
_COINS_PER_MINUTE = 20
_SECONDS_PER_COIN = 60 / _COINS_PER_MINUTE  # 3 seconds
_FETCH_TIMEOUT = 15  # seconds per coin

# Pre-computed results cache - now includes timeframe in key
# Format: _precomputed_results["strat_1_1h"] = [results...]
_precomputed_results: Dict[str, List[Dict[str, Any]]] = {}
_last_precompute_time: Dict[str, float] = {}  # Track time per timeframe
_precompute_lock = asyncio.Lock()
_is_precomputing: Dict[str, bool] = {}  # Track precomputing status per timeframe


def _get_cache_key(strategy_key: str, timeframe: str) -> str:
    """Generate cache key combining strategy and timeframe."""
    return f"{strategy_key}_{timeframe}"


def safe_get(d: Optional[Dict], key: str, default: Any = None) -> Any:
    """Safely get value from dict, handling None dicts."""
    if d is None or not isinstance(d, dict):
        return default
    return d.get(key, default)


def safe_float_compare(val: Any, default: float = float('inf')) -> float:
    """Convert value to float for comparison, return default if invalid."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


async def _fetch_for_coin(symbol: str, timeframe: str) -> Tuple[str, Optional[Dict]]:
    """
    Fetch screener data for a single coin.
    Returns tuple (symbol, screener_data_dict) or (symbol, None) on failure.
    """
    try:
        screener_data = await asyncio.wait_for(
            load_screener_data(symbol + "/USDT", interval=timeframe),
            timeout=_FETCH_TIMEOUT
        )
        return symbol, screener_data
    except asyncio.TimeoutError:
        print(f"[screener] timeout for {symbol} ({timeframe})")
        return symbol, None
    except Exception as e:
        print(f"[screener] fetch error for {symbol} ({timeframe}): {e}")
        return symbol, None


async def precompute_all_coins(timeframe: str = "1h") -> None:
    """
    Pre-fetch and cache data for all 100 coins for a specific timeframe.
    Respects rate limit of 20 coins/minute = 1 coin every 3 seconds.
    This takes ~5 minutes to complete for 100 coins.
    """
    global _last_precompute_time, _is_precomputing
    
    async with _precompute_lock:
        if _is_precomputing.get(timeframe, False):
            print(f"[screener] Pre-computation already in progress for {timeframe}, skipping...")
            return
        
        _is_precomputing[timeframe] = True
        print(f"[screener] Starting pre-computation for {len(COINS_LIST)} coins on {timeframe} timeframe...")
        start_time = time.time()
        
        try:
            all_data = {}
            
            # Fetch coins sequentially with rate limiting
            for i, coin in enumerate(COINS_LIST, 1):
                symbol = coin["symbol"]
                
                # Fetch data
                _, screener_data = await _fetch_for_coin(symbol, timeframe)
                
                if screener_data:
                    all_data[symbol] = screener_data
                    print(f"[screener] Fetched {i}/{len(COINS_LIST)}: {symbol} ({timeframe})")
                else:
                    print(f"[screener] Failed to fetch {i}/{len(COINS_LIST)}: {symbol} ({timeframe})")
                
                # Rate limiting: wait 3 seconds between coins (except last one)
                if i < len(COINS_LIST):
                    await asyncio.sleep(_SECONDS_PER_COIN)
            
            # Now compute results for all strategies
            for strategy_key in ["strat_1", "strat_2", "strat_3", "strat_4", "strat_5"]:
                matches = []
                
                for symbol, screener_data in all_data.items():
                    payload = screener_data.copy()
                    payload["symbol"] = symbol
                    
                    try:
                        matched, score = match_strategy(strategy_key, payload)
                        if matched and score > 0:
                            matches.append({
                                "symbol": symbol,
                                "rsi": safe_get(payload, "rsi"),
                                "macd": safe_get(payload, "macd"),
                                "macd_signal": safe_get(payload, "signal"),
                                "close": safe_get(payload, "close"),
                                "score": score,
                            })
                    except Exception as e:
                        print(f"[screener] Error matching {symbol} for {strategy_key}: {e}")
                
                # Sort matches
                matches.sort(key=lambda x: (
                    -x["score"],
                    safe_float_compare(x["rsi"])
                ))
                
                # Store with timeframe-specific key
                cache_key = _get_cache_key(strategy_key, timeframe)
                _precomputed_results[cache_key] = matches
            
            _last_precompute_time[timeframe] = time.time()
            elapsed = time.time() - start_time
            print(f"[screener] Pre-computation completed for {timeframe} in {elapsed:.1f}s")
            
        finally:
            _is_precomputing[timeframe] = False


def get_precomputed_results(strategy_key: str, timeframe: str = "1h") -> Optional[List[Dict[str, Any]]]:
    """
    Get pre-computed results for a strategy and timeframe.
    Returns None if no pre-computed data available.
    """
    cache_key = _get_cache_key(strategy_key, timeframe)
    return _precomputed_results.get(cache_key)


def is_cache_fresh(timeframe: str = "1h", max_age_seconds: int = 300) -> bool:
    """Check if pre-computed cache is still fresh (< 5 minutes old) for a specific timeframe."""
    last_time = _last_precompute_time.get(timeframe, 0)
    if last_time == 0:
        return False
    age = time.time() - last_time
    return age < max_age_seconds


async def run_screener(strategy_key: str, timeframe: str = "1h", use_precomputed: bool = True) -> List[Dict[str, Any]]:
    """
    Scan coins and match strategy_key for a specific timeframe.
    
    Args:
        strategy_key: The strategy to match (e.g., "strat_1")
        timeframe: The timeframe to analyze (e.g., "1h", "4h", "1d")
        use_precomputed: Whether to use cached results (default: True)
    
    If use_precomputed=True (default):
        - Returns instant results from pre-computed cache if available
        - Falls back to live scan if cache is empty or stale
    
    If use_precomputed=False:
        - Always performs live scan (slower, for testing)
    
    Returns list of matches sorted by relevance.
    """
    # Try to use pre-computed results first
    if use_precomputed:
        results = get_precomputed_results(strategy_key, timeframe)
        if results is not None:
            print(f"[screener] Returning {len(results)} pre-computed results for {strategy_key} ({timeframe})")
            return results
        else:
            print(f"[screener] No pre-computed results available for {timeframe}, falling back to live scan")
    
    # Fall back to live scan
    return await _run_live_screener(strategy_key, timeframe)


async def _run_live_screener(strategy_key: str, timeframe: str = "1h", limit: int = 100) -> List[Dict[str, Any]]:
    """
    Perform live scan of coins (slower, respects rate limits).
    Used as fallback when pre-computed cache is empty.
    """
    if not COINS_LIST:
        print("[screener] No coins available to scan")
        return []

    print(f"[screener] Starting live scan for {strategy_key} on {timeframe}...")
    matches = []
    limit = min(limit, len(COINS_LIST))
    
    # Fetch coins sequentially with rate limiting
    for i, coin in enumerate(COINS_LIST[:limit], 1):
        symbol = coin["symbol"]
        
        _, screener_data = await _fetch_for_coin(symbol, timeframe)
        
        if not screener_data:
            continue
        
        payload = screener_data.copy()
        payload["symbol"] = symbol
        
        try:
            matched, score = match_strategy(strategy_key, payload)
            if matched and score > 0:
                matches.append({
                    "symbol": symbol,
                    "rsi": safe_get(payload, "rsi"),
                    "macd": safe_get(payload, "macd"),
                    "macd_signal": safe_get(payload, "signal"),
                    "close": safe_get(payload, "close"),
                    "score": score,
                })
        except Exception as e:
            print(f"[screener] match_strategy error for {symbol}: {e}")
        
        # Rate limiting: wait 3 seconds between coins
        if i < limit:
            await asyncio.sleep(_SECONDS_PER_COIN)
    
    # Sort matches
    matches.sort(key=lambda x: (
        -x["score"],
        safe_float_compare(x["rsi"])
    ))
    
    print(f"[screener] Live scan completed for {timeframe}: {len(matches)} matches found")
    return matches


def _validate_number(val: Any) -> bool:
    """Check if value is a valid number (not None, not NaN, not inf)."""
    if val is None:
        return False
    try:
        num = float(val)
        return not (num != num or num == float('inf') or num == float('-inf'))
    except (ValueError, TypeError):
        return False



def match_strategy(key: str, d: Dict[str, Any]) -> Tuple[bool, int]:
    """
    Match a coin against a strategy with REALISTIC thresholds.
    
    FIXED: Relaxed requirements to find actual opportunities.
    Each strategy now has multiple scoring paths and lower thresholds.
    
    Returns (match_bool, score_int).
    """
    score = 0
    
    # Extract indicators
    rsi = safe_get(d, "rsi")
    macd = safe_get(d, "macd")
    signal = safe_get(d, "signal")
    ema20 = safe_get(d, "ema20")
    ema50 = safe_get(d, "ema50")
    ema200 = safe_get(d, "ema200")
    close = safe_get(d, "close")
    prev_close = safe_get(d, "prev_close")
    volume = safe_get(d, "volume")
    volume_ma = safe_get(d, "volume_ma")
    avg_7d = safe_get(d, "avg_7d")
    resistance = safe_get(d, "resistance")
    support = safe_get(d, "support")
    bullish_engulfing = safe_get(d, "bullish_engulfing", False)

    # ========================================================================
    # STRATEGY 1: Strong Bounce Setup
    # OLD: Required RSI < 30 + bullish MACD (score >= 3)
    # NEW: Multiple paths to qualify
    # ========================================================================
    if key == "strat_1":
        # Path 1: Oversold RSI (relaxed)
        if _validate_number(rsi):
            if rsi < 35:  # Relaxed from 30
                score += 2
                if rsi < 25:
                    score += 1
            elif 35 <= rsi <= 45:  # Recovery zone
                score += 1
        
        # Path 2: Bullish MACD momentum
        if _validate_number(macd) and _validate_number(signal):
            if macd > signal:
                score += 2
                hist_strength = abs(macd - signal) / abs(signal) if signal != 0 else 0
                if hist_strength > 0.05:  # 5% above signal
                    score += 1
        
        # Path 3: Price near support
        if _validate_number(close) and _validate_number(support):
            dist = ((close - support) / support) * 100
            if -2 <= dist <= 5:  # Within 2% below to 5% above support
                score += 1
        
        # MATCH: Need score >= 2 (not 3)
        return score >= 2, score

    # ========================================================================
    # STRATEGY 2: Breakout with Momentum
    # OLD: Required exact EMA crossover + high volume (score >= 4)
    # NEW: Proximity to breakout OR recent breakout
    # ========================================================================
    elif key == "strat_2":
        # Path 1: Near or above EMA20
        if all(_validate_number(x) for x in [close, ema20]):
            dist_from_ema = ((close - ema20) / ema20) * 100
            
            if dist_from_ema > 0:  # Above EMA20
                score += 2
                if dist_from_ema > 2:  # Strongly above
                    score += 1
            elif -2 <= dist_from_ema <= 0:  # Near EMA (within 2%)
                score += 1
        
        # Path 2: Recent price momentum
        if _validate_number(close) and _validate_number(prev_close):
            if close > prev_close:
                pct_gain = ((close - prev_close) / prev_close) * 100
                if pct_gain >= 1:
                    score += 1
                if pct_gain >= 3:
                    score += 1
        
        # Path 3: Volume confirmation (relaxed)
        if _validate_number(volume) and _validate_number(volume_ma) and volume_ma > 0:
            volume_ratio = volume / volume_ma
            if volume_ratio >= 1.2:  # Relaxed from 1.5x
                score += 1
                if volume_ratio >= 1.8:
                    score += 1
        
        # MATCH: Need score >= 3 (not 4)
        return score >= 3, score

    # ========================================================================
    # STRATEGY 3: Reversal After Sell-Off
    # OLD: Required RSI < 30 + bullish engulfing (score >= 4)
    # NEW: Signs of bottoming out
    # ========================================================================
    elif key == "strat_3":
        # Path 1: Oversold conditions (relaxed)
        if _validate_number(rsi):
            if rsi < 35:
                score += 2
                if rsi < 25:
                    score += 1
            elif 35 <= rsi <= 40:  # Early recovery
                score += 1
        
        # Path 2: Bullish candlestick pattern
        if bullish_engulfing:
            score += 2
        else:
            # Check for pattern manually
            c1 = safe_get(d, "candle_1")
            c2 = safe_get(d, "candle_2")
            if c1 and c2 and isinstance(c1, dict) and isinstance(c2, dict):
                try:
                    if is_bullish_engulfing(c1, c2):
                        score += 2
                except Exception:
                    pass
        
        # Path 3: Price recovery
        if _validate_number(close) and _validate_number(prev_close):
            if close > prev_close:
                score += 1
        
        # Path 4: Near support level
        if _validate_number(close) and _validate_number(support):
            dist = abs(close - support) / support * 100
            if dist <= 3:  # Within 3% of support
                score += 1
        
        # MATCH: Need score >= 3 (not 4)
        return score >= 3, score

    # ========================================================================
    # STRATEGY 4: Trend Turning Bullish
    # OLD: Required MACD > signal + EMA50 > EMA200 (score >= 3)
    # NEW: Signs of trend improvement
    # ========================================================================
    elif key == "strat_4":
        # Path 1: Bullish MACD
        if _validate_number(macd) and _validate_number(signal):
            if macd > signal * 0.95:  # Near or above signal
                score += 1
                if macd > signal:
                    score += 1
                    if macd > signal * 1.05:
                        score += 1
        
        # Path 2: EMA alignment (relaxed)
        if _validate_number(ema50) and _validate_number(ema200):
            if ema50 > ema200 * 0.98:  # Near or above
                score += 1
                if ema50 > ema200:
                    score += 1
        
        # Path 3: Price above EMAs
        if _validate_number(close) and _validate_number(ema20):
            if close > ema20:
                score += 1
        
        # MATCH: Need score >= 2 (not 3)
        return score >= 2, score

    # ========================================================================
    # STRATEGY 5: Deep Pullback Opportunity
    # OLD: Required 5%+ drop from 7-day avg (score >= 3)
    # NEW: Healthy pullback in uptrend
    # ========================================================================
    elif key == "strat_5":
        # Path 1: Price below recent average (FIXED logic)
        if _validate_number(avg_7d) and _validate_number(close):
            pct_below = ((avg_7d - close) / avg_7d) * 100
            
            # FIXED: We want 2-8% below average (healthy pullback)
            if 2 <= pct_below <= 8:
                score += 2
                if 3 <= pct_below <= 6:  # Sweet spot
                    score += 1
        
        # Path 2: Near support (opportunity zone)
        if _validate_number(support) and _validate_number(close):
            dist_from_support = ((close - support) / support) * 100
            if 0 <= dist_from_support <= 5:  # 0-5% above support
                score += 2
                if dist_from_support <= 2:
                    score += 1
        
        # Path 3: Still in uptrend (confirmation)
        if _validate_number(close) and _validate_number(ema50):
            if close > ema50 * 0.95:  # Not too far below EMA50
                score += 1
        
        # Path 4: RSI not oversold (healthy correction)
        if _validate_number(rsi):
            if 40 <= rsi <= 55:  # Pullback but not oversold
                score += 1
        
        # MATCH: Need score >= 2 (not 3)
        return score >= 2, score

    return False, 0

