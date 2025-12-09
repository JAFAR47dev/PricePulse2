# services/screener.py
import asyncio
import json
import os
from typing import Dict, Any

from utils.indicators import get_crypto_indicators
from services.screener_data import load_screener_data, is_bullish_engulfing

# Load top 200 coin IDs (symbol -> id)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COINGECKO_IDS_PATH = os.path.join(BASE_DIR, "services", "coingecko_ids.json")
with open(COINGECKO_IDS_PATH, "r") as f:
    TOP_200_COINS = json.load(f)

COINS_LIST = [{"symbol": symbol.upper(), "id": cid} for symbol, cid in TOP_200_COINS.items()]


# tune concurrency to avoid burst
_CONCURRENCY = 8


async def _fetch_for_coin(symbol: str, timeframe: str, sem: asyncio.Semaphore):
    """
    Fetch both the indicator pack (fast) and the extended screener data (price/volume/daily history).
    Returns tuple (symbol, indicators_dict, screener_data_dict) or (symbol, None, None) on failure.
    """
    async with sem:
        try:
            # Launch both fetches concurrently
            ind_task = asyncio.create_task(get_crypto_indicators(symbol + "/USD", interval=timeframe))
            data_task = asyncio.create_task(load_screener_data(symbol + "/USD", interval=timeframe))

            indicators, screener_data = await asyncio.gather(ind_task, data_task)

            return symbol, indicators, screener_data

        except Exception as e:
            # safe fail for a single coin
            print(f"[screener] fetch error for {symbol}: {e}")
            return symbol, None, None


async def run_screener(strategy_key: str, timeframe: str = "1h", limit: int = 100):
    """
    Scan top coins (COINS_LIST) and match strategy_key.
    Returns list of matches sorted by relevance (default: RSI ascending for oversold strategies).
    """
    matches = []
    sem = asyncio.Semaphore(_CONCURRENCY)

    # clamp limit to available coins
    limit = min(limit, len(COINS_LIST))

    # create fetch tasks
    tasks = [
        asyncio.create_task(_fetch_for_coin(coin["symbol"], timeframe, sem))
        for coin in COINS_LIST[:limit]
    ]

    # gather results (will continue even if some tasks fail)
    for coro in asyncio.as_completed(tasks):
        try:
            symbol, indicators, screener_data = await coro
        except Exception as e:
            print("[screener] task error:", e)
            continue

        if not indicators:
            # no indicator pack — skip
            continue

        # Combine the two sources into a single dict for matching
        payload = {}
        payload.update(indicators)             # price, ema20, rsi, macd, ...
        if screener_data:
            # these keys come from your load_screener_data
            payload.update({
                "close": screener_data.get("close"),
                "prev_close": screener_data.get("prev_close"),
                "volume": screener_data.get("volume"),
                "volume_ma": screener_data.get("volume_ma"),
                "candle_1": screener_data.get("candle_1"),
                "candle_2": screener_data.get("candle_2"),
                "avg_7d": screener_data.get("avg_7d"),
                "resistance": screener_data.get("resistance"),
                "support": screener_data.get("support"),
                # keep flag if screener_data detected a bullish engulfing
                "bullish_engulfing": screener_data.get("bullish_engulfing", False),
            })

        # Run strategy matcher
        try:
            matched, score = match_strategy(strategy_key, payload)
        except Exception as e:
            print(f"[screener] match_strategy error for {symbol}: {e}")
            matched, score = False, 0

        if matched:
            matches.append({
                "symbol": symbol,
                "rsi": payload.get("rsi"),
                "macd": payload.get("macd"),
                "macd_signal": payload.get("macdSignal"),
                "close": payload.get("price") or payload.get("close"),
                "score": score,
            })

    # Default sorting: by RSI ascending (oversold strongest). If RSI missing, put to the back.
    matches.sort(key=lambda x: (x["rsi"] is None, x["rsi"] if x["rsi"] is not None else 999))
    return matches


def match_strategy(key: str, d: Dict[str, Any]):
    """
    Accepts a single combined indicator dict `d` composed of:
      - price fields (price, close, prev_close)
      - indicators (rsi, macd, macdSignal, ema20, ema50, ema200, ...)
      - screener metadata (volume, volume_ma, avg_7d, resistance, support, bullish_engulfing)

    Returns (match_bool, score_int)
    """
    # safe helpers
    def f(k): return d.get(k)
    rsi = f("rsi")
    macd = f("macd")
    signal = f("macdSignal") or f("macd_signal") or f("signal")
    ema20 = f("ema20")
    ema50 = f("ema50")
    ema200 = f("ema200")
    close = f("price") or f("close")
    prev_close = f("prev_close")
    volume = f("volume")
    volume_ma = f("volume_ma")
    avg_7d = f("avg_7d")
    resistance = f("resistance")
    support = f("support")
    bullish_engulfing = f("bullish_engulfing") or False

    score = 0

    # === STRATEGY 1: RSI < 30 + MACD Bullish Crossover/Momentum ===
    if key == "strat_1":
        if rsi is not None and rsi < 30:
            score += 1

        # prefer true crossover detection if we had history, but using momentum (macd > signal) is acceptable
        if macd is not None and signal is not None and macd > signal:
            score += 1

        return score == 2, score

    # === STRATEGY 2: EMA Breakout + Volume Surge ===
    elif key == "strat_2":
        # Condition 1: real breakout (prev_close < ema20 and close > ema20)
        if prev_close is not None and ema20 is not None and close is not None:
            if prev_close < ema20 and close > ema20:
                score += 1

        # Condition 2: volume surge (current volume >= 1.5 * volume_ma)
        if volume is not None and volume_ma is not None:
            if volume >= (volume_ma * 1.5):
                score += 1

        return score == 2, score

    # === STRATEGY 3: RSI Oversold + Bullish Engulfing ===
    elif key == "strat_3":
        if rsi is not None and rsi < 30:
            score += 1

        # Use screener_data's engulfing flag if present, otherwise try to detect from candles if present
        if bullish_engulfing:
            score += 1
        else:
            c1 = d.get("candle_1")
            c2 = d.get("candle_2")
            if c1 and c2 and is_bullish_engulfing(c1, c2):
                score += 1

        return score == 2, score

    # === STRATEGY 4: MACD Bullish + EMA50 > EMA200 (Golden Cross) ===
    elif key == "strat_4":
        if macd is not None and signal is not None and macd > signal:
            score += 1

        if ema50 is not None and ema200 is not None and ema50 > ema200:
            score += 1

        return score == 2, score

    # === STRATEGY 5: Price 5% below 7d avg + Trendline Break ===
    elif key == "strat_5":
        if avg_7d is not None and close is not None and close < (avg_7d * 0.95):
            score += 1

        # trendline break: current price greater than resistance (breakout) OR below support (breakdown)
        trendline_break = False
        if resistance is not None and close is not None and close > resistance:
            trendline_break = True
        if support is not None and close is not None and close < support:
            trendline_break = True

        if trendline_break:
            score += 1

        return score == 2, score

    # Unknown strategy
    return False, 0