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
# Format: _precomputed_results["strat_1_1h"] = [results...]
_precomputed_results: Dict[str, List[Dict[str, Any]]] = {}
_last_precompute_time: Dict[str, float] = {}
_is_precomputing: Dict[str, bool] = {}  # Track per-timeframe status

# FIX: Lock only protects the _is_precomputing flag check, NOT the full operation.
# This allows multiple timeframes to precompute concurrently without blocking each other.
_precompute_flag_lock = asyncio.Lock()


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
    Takes ~5 minutes per timeframe.

    FIX: The lock now only guards the is_precomputing flag check.
    The actual fetch+compute runs outside the lock so other timeframes
    can start their own precomputation concurrently without waiting.
    """
    # --- Only lock long enough to check/set the flag ---
    async with _precompute_flag_lock:
        if _is_precomputing.get(timeframe, False):
            print(f"[screener] Pre-computation already in progress for {timeframe}, skipping...")
            return
        _is_precomputing[timeframe] = True
    # --- Lock released immediately, heavy work runs freely below ---

    print(f"[screener] Starting pre-computation for {len(COINS_LIST)} coins on {timeframe}...")
    start_time = time.time()

    try:
        all_data = {}

        for i, coin in enumerate(COINS_LIST, 1):
            symbol = coin["symbol"]

            _, screener_data = await _fetch_for_coin(symbol, timeframe)

            if screener_data:
                all_data[symbol] = screener_data
                print(f"[screener] Fetched {i}/{len(COINS_LIST)}: {symbol} ({timeframe})")
            else:
                print(f"[screener] Failed {i}/{len(COINS_LIST)}: {symbol} ({timeframe})")

            if i < len(COINS_LIST):
                await asyncio.sleep(_SECONDS_PER_COIN)

        # Compute and store results for all strategies
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

            matches.sort(key=lambda x: (
                -x["score"],
                safe_float_compare(x["rsi"])
            ))

            cache_key = _get_cache_key(strategy_key, timeframe)
            _precomputed_results[cache_key] = matches

        _last_precompute_time[timeframe] = time.time()
        elapsed = time.time() - start_time
        print(f"[screener] ✅ Pre-computation done for {timeframe} in {elapsed:.1f}s")

    except Exception as e:
        print(f"[screener] ❌ Pre-computation failed for {timeframe}: {e}")

    finally:
        # Always clear the flag, even if an exception occurred
        _is_precomputing[timeframe] = False


def get_precomputed_results(strategy_key: str, timeframe: str = "1h") -> Optional[List[Dict[str, Any]]]:
    """
    Get pre-computed results for a strategy and timeframe.
    Returns None if no pre-computed data available.
    """
    cache_key = _get_cache_key(strategy_key, timeframe)
    return _precomputed_results.get(cache_key)


def is_cache_fresh(timeframe: str = "1h", max_age_seconds: int = 3600) -> bool:
    """
    Check if pre-computed cache is still fresh for a specific timeframe.

    FIX: Default max_age_seconds changed from 300 (5 min) to 3600 (1 hour)
    to match the actual job interval. The old 300s default meant the cache
    was considered stale almost immediately after being built, causing
    unnecessary live scans.
    """
    last_time = _last_precompute_time.get(timeframe, 0)
    if last_time == 0:
        return False
    return (time.time() - last_time) < max_age_seconds


async def run_screener(strategy_key: str, timeframe: str = "1h", use_precomputed: bool = True) -> List[Dict[str, Any]]:
    """
    Return screener results for a strategy and timeframe.

    Uses pre-computed cache when available (instant).
    Falls back to live scan only if cache is completely empty.
    """
    if use_precomputed:
        results = get_precomputed_results(strategy_key, timeframe)
        if results is not None:
            print(f"[screener] ⚡ Returning {len(results)} cached results for {strategy_key} ({timeframe})")
            return results
        else:
            print(f"[screener] No cache for {timeframe}, falling back to live scan")

    return await _run_live_screener(strategy_key, timeframe)


async def _run_live_screener(strategy_key: str, timeframe: str = "1h", limit: int = 100) -> List[Dict[str, Any]]:
    """
    Live scan fallback — used only when cache is completely empty.
    Slow by design (rate-limited). Triggers background cache warmup
    so the next call will be instant.
    """
    if not COINS_LIST:
        print("[screener] No coins available to scan")
        return []

    print(f"[screener] Starting live scan for {strategy_key} on {timeframe}...")

    # FIX: Trigger background precompute so next request hits cache.
    # Only trigger if not already running for this timeframe.
    if not _is_precomputing.get(timeframe, False):
        print(f"[screener] Triggering background precompute for {timeframe}...")
        asyncio.create_task(precompute_all_coins(timeframe=timeframe))

    matches = []
    limit = min(limit, len(COINS_LIST))

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

        if i < limit:
            await asyncio.sleep(_SECONDS_PER_COIN)

    matches.sort(key=lambda x: (
        -x["score"],
        safe_float_compare(x["rsi"])
    ))

    print(f"[screener] Live scan done for {timeframe}: {len(matches)} matches")
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
    Returns (match_bool, score_int).
    """
    score = 0

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

    if key == "strat_1":
        if _validate_number(rsi):
            if rsi < 35:
                score += 2
                if rsi < 25:
                    score += 1
            elif 35 <= rsi <= 45:
                score += 1

        if _validate_number(macd) and _validate_number(signal):
            if macd > signal:
                score += 2
                hist_strength = abs(macd - signal) / abs(signal) if signal != 0 else 0
                if hist_strength > 0.05:
                    score += 1

        if _validate_number(close) and _validate_number(support):
            dist = ((close - support) / support) * 100
            if -2 <= dist <= 5:
                score += 1

        return score >= 2, score

    elif key == "strat_2":
        if all(_validate_number(x) for x in [close, ema20]):
            dist_from_ema = ((close - ema20) / ema20) * 100
            if dist_from_ema > 0:
                score += 2
                if dist_from_ema > 2:
                    score += 1
            elif -2 <= dist_from_ema <= 0:
                score += 1

        if _validate_number(close) and _validate_number(prev_close):
            if close > prev_close:
                pct_gain = ((close - prev_close) / prev_close) * 100
                if pct_gain >= 1:
                    score += 1
                if pct_gain >= 3:
                    score += 1

        if _validate_number(volume) and _validate_number(volume_ma) and volume_ma > 0:
            volume_ratio = volume / volume_ma
            if volume_ratio >= 1.2:
                score += 1
                if volume_ratio >= 1.8:
                    score += 1

        return score >= 3, score

    elif key == "strat_3":
        if _validate_number(rsi):
            if rsi < 35:
                score += 2
                if rsi < 25:
                    score += 1
            elif 35 <= rsi <= 40:
                score += 1

        if bullish_engulfing:
            score += 2
        else:
            c1 = safe_get(d, "candle_1")
            c2 = safe_get(d, "candle_2")
            if c1 and c2 and isinstance(c1, dict) and isinstance(c2, dict):
                try:
                    if is_bullish_engulfing(c1, c2):
                        score += 2
                except Exception:
                    pass

        if _validate_number(close) and _validate_number(prev_close):
            if close > prev_close:
                score += 1

        if _validate_number(close) and _validate_number(support):
            dist = abs(close - support) / support * 100
            if dist <= 3:
                score += 1

        return score >= 3, score

    elif key == "strat_4":
        if _validate_number(macd) and _validate_number(signal):
            if macd > signal * 0.95:
                score += 1
                if macd > signal:
                    score += 1
                    if macd > signal * 1.05:
                        score += 1

        if _validate_number(ema50) and _validate_number(ema200):
            if ema50 > ema200 * 0.98:
                score += 1
                if ema50 > ema200:
                    score += 1

        if _validate_number(close) and _validate_number(ema20):
            if close > ema20:
                score += 1

        return score >= 2, score

    elif key == "strat_5":
        if _validate_number(avg_7d) and _validate_number(close):
            pct_below = ((avg_7d - close) / avg_7d) * 100
            if 2 <= pct_below <= 8:
                score += 2
                if 3 <= pct_below <= 6:
                    score += 1

        if _validate_number(support) and _validate_number(close):
            dist_from_support = ((close - support) / support) * 100
            if 0 <= dist_from_support <= 5:
                score += 2
                if dist_from_support <= 2:
                    score += 1

        if _validate_number(close) and _validate_number(ema50):
            if close > ema50 * 0.95:
                score += 1

        if _validate_number(rsi):
            if 40 <= rsi <= 55:
                score += 1

        return score >= 2, score

    return False, 0
