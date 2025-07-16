
import json
from utils.ohlcv import fetch_candles

# Load top 200 coin IDs (symbol + id mapping)
with open("utils/coingecko_ids.json", "r") as f:
    TOP_200_COINS = json.load(f)

# Convert dict to list of dicts for iteration
COINS_LIST = [{"symbol": symbol, "id": coin_id} for symbol, coin_id in TOP_200_COINS.items()]

async def run_screener(strategy_key: str, timeframe: str = "1h", limit: int = 100):
    matches = []

    for coin in COINS_LIST[:limit]:  # slice works now on list
        symbol = coin["symbol"].upper()

        candles = await fetch_candles(symbol, tf=timeframe)
        if not candles or len(candles) < 50:
            continue

        latest = candles[-1]
        if match_strategy(strategy_key, latest, candles):
            matches.append({
                "symbol": symbol,
                "rsi": latest.get("rsi"),
                "macd": latest.get("macd"),
                "macd_signal": latest.get("macdSignal"),
                "close": latest.get("close"),
            })

    # Sort by RSI ascending (strongest oversold)
    matches.sort(key=lambda x: x["rsi"] or 50)
    return matches

def match_strategy(key: str, latest, candles):
    """Returns (match_found: bool, signal_strength_score: int)"""
    rsi = latest.get("rsi", 50)
    macd = latest.get("macd", 0)
    signal = latest.get("macdSignal", 0)
    ema = latest.get("ema", 0)
    close = latest.get("close", 0)
    score = 0

    if key == "strat_1":  # RSI < 30 + MACD crossover
        if rsi < 30: score += 1
        if macd > signal: score += 1
        return score == 2, score

    elif key == "strat_2":  # EMA Breakout
        if close > ema: score += 1
        return score == 1, score

    elif key == "strat_3":  # RSI Oversold
        if rsi < 30: score += 1
        return score == 1, score

    elif key == "strat_4":  # MACD Bullish + MACD > 0
        if macd > signal: score += 1
        if macd > 0: score += 1
        return score == 2, score

    elif key == "strat_5":  # Price 5% below 7d average
        avg_price = sum([c["close"] for c in candles[-168:]]) / 168
        if close < 0.95 * avg_price: score += 1
        return score == 1, score

    return False, 0