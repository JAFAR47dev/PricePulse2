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

# Pre-computed results cache
_precomputed_results: Dict[str, List[Dict[str, Any]]] = {}
_last_precompute_time: float = 0
_precompute_lock = asyncio.Lock()
_is_precomputing = False


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
            load_screener_data(symbol + "/USD", interval=timeframe),
            timeout=_FETCH_TIMEOUT
        )
        return symbol, screener_data
    except asyncio.TimeoutError:
        print(f"[screener] timeout for {symbol}")
        return symbol, None
    except Exception as e:
        print(f"[screener] fetch error for {symbol}: {e}")
        return symbol, None


async def precompute_all_coins(timeframe: str = "1h") -> None:
    """
    Pre-fetch and cache data for all 100 coins.
    Respects rate limit of 20 coins/minute = 1 coin every 3 seconds.
    This takes ~5 minutes to complete for 100 coins.
    """
    global _last_precompute_time, _is_precomputing
    
    async with _precompute_lock:
        if _is_precomputing:
            print("[screener] Pre-computation already in progress, skipping...")
            return
        
        _is_precomputing = True
        print(f"[screener] Starting pre-computation for {len(COINS_LIST)} coins...")
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
                    print(f"[screener] Fetched {i}/{len(COINS_LIST)}: {symbol}")
                else:
                    print(f"[screener] Failed to fetch {i}/{len(COINS_LIST)}: {symbol}")
                
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
                
                _precomputed_results[strategy_key] = matches
            
            _last_precompute_time = time.time()
            elapsed = time.time() - start_time
            print(f"[screener] Pre-computation completed in {elapsed:.1f}s")
            
        finally:
            _is_precomputing = False


def get_precomputed_results(strategy_key: str) -> Optional[List[Dict[str, Any]]]:
    """
    Get pre-computed results for a strategy.
    Returns None if no pre-computed data available.
    """
    return _precomputed_results.get(strategy_key)


def is_cache_fresh(max_age_seconds: int = 300) -> bool:
    """Check if pre-computed cache is still fresh (< 5 minutes old)."""
    if _last_precompute_time == 0:
        return False
    age = time.time() - _last_precompute_time
    return age < max_age_seconds


async def run_screener(strategy_key: str, timeframe: str = "1h", use_precomputed: bool = True) -> List[Dict[str, Any]]:
    """
    Scan coins and match strategy_key.
    
    If use_precomputed=True (default):
        - Returns instant results from pre-computed cache if available
        - Falls back to live scan if cache is empty or stale
    
    If use_precomputed=False:
        - Always performs live scan (slower, for testing)
    
    Returns list of matches sorted by relevance.
    """
    # Try to use pre-computed results first
    if use_precomputed:
        results = get_precomputed_results(strategy_key)
        if results is not None:
            print(f"[screener] Returning {len(results)} pre-computed results for {strategy_key}")
            return results
        else:
            print(f"[screener] No pre-computed results available, falling back to live scan")
    
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

    print(f"[screener] Starting live scan for {strategy_key}...")
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
    
    print(f"[screener] Live scan completed: {len(matches)} matches found")
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
    Match a coin against a strategy.
    Returns (match_bool, score_int).
    """
    score = 0
    
    # Extract and validate all indicators
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

    # STRATEGY 1: Strong Bounce Setup
    if key == "strat_1":
        if _validate_number(rsi) and rsi < 30:
            score += 2
            if rsi < 25:
                score += 1
        if _validate_number(macd) and _validate_number(signal):
            if macd > signal:
                score += 2
                if macd > signal * 1.1:
                    score += 1
        return score >= 3, score

    # STRATEGY 2: Breakout with Momentum
    elif key == "strat_2":
        if all(_validate_number(x) for x in [prev_close, ema20, close]):
            if prev_close < ema20 and close > ema20:
                score += 3
                pct_above = ((close - ema20) / ema20) * 100
                if pct_above > 1:
                    score += 1
        if _validate_number(volume) and _validate_number(volume_ma) and volume_ma > 0:
            volume_ratio = volume / volume_ma
            if volume_ratio >= 1.5:
                score += 2
                if volume_ratio >= 2.0:
                    score += 1
        return score >= 4, score

    # STRATEGY 3: Reversal After Sell-Off
    elif key == "strat_3":
        if _validate_number(rsi) and rsi < 30:
            score += 2
            if rsi < 25:
                score += 1
        if bullish_engulfing:
            score += 3
        else:
            c1 = safe_get(d, "candle_1")
            c2 = safe_get(d, "candle_2")
            if c1 and c2 and isinstance(c1, dict) and isinstance(c2, dict):
                try:
                    if is_bullish_engulfing(c1, c2):
                        score += 3
                except Exception:
                    pass
        return score >= 4, score

    # STRATEGY 4: Trend Turning Bullish
    elif key == "strat_4":
        if _validate_number(macd) and _validate_number(signal):
            if macd > signal:
                score += 2
                if macd > signal * 1.05:
                    score += 1
        if _validate_number(ema50) and _validate_number(ema200):
            if ema50 > ema200:
                score += 2
                pct_diff = ((ema50 - ema200) / ema200) * 100
                if pct_diff > 2:
                    score += 1
        return score >= 3, score

    # STRATEGY 5: Deep Pullback Opportunity
    elif key == "strat_5":
        if _validate_number(avg_7d) and _validate_number(close):
            pct_below = ((avg_7d - close) / avg_7d) * 100
            if pct_below >= 5:
                score += 2
                if pct_below >= 8:
                    score += 1
        if _validate_number(support) and _validate_number(close):
            dist_from_support = abs(close - support) / support * 100
            if dist_from_support <= 2:
                score += 2
                if close >= support and dist_from_support <= 1:
                    score += 1
        if _validate_number(resistance) and _validate_number(close):
            if close > resistance:
                score += 1
        return score >= 3, score

    return False, 0