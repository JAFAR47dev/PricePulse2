# services/screener_data.py

import aiohttp
import os
from dotenv import load_dotenv

load_dotenv()
TWELVE_DATA_API = os.getenv("TWELVE_DATA_API_KEY")

BASE_URL = "https://api.twelvedata.com"


# ------------------------------
# Generic JSON Fetcher
# ------------------------------
async def fetch_json(url):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as r:
                if r.status != 200:
                    return None
                return await r.json()
        except:
            return None


# ------------------------------
# General Indicator Fetcher
# ------------------------------
async def get_indicator(symbol: str, interval: str, indicator: str, params: str = ""):
    url = f"{BASE_URL}/{indicator}?symbol={symbol}&interval={interval}&apikey={TWELVE_DATA_API}{params}"
    return await fetch_json(url)


# ------------------------------
# Historical Data Fetcher
# ------------------------------
async def get_historical(symbol: str, interval: str, limit: int = 100):
    """
    Fetches historical candles sorted newest → oldest.
    """
    url = f"{BASE_URL}/time_series?symbol={symbol}&interval={interval}&apikey={TWELVE_DATA_API}&outputsize={limit}"
    data = await fetch_json(url)

    if not data or "values" not in data:
        return None

    return data["values"]  # Already newest first


# ------------------------------
# Bullish Engulfing Detector
# ------------------------------
def is_bullish_engulfing(c1, c2):
    """
    c1 = previous candle
    c2 = current candle
    {"open": float, "close": float}
    """

    # Candle 1 bearish
    if c1["close"] >= c1["open"]:
        return False

    # Candle 2 bullish
    if c2["close"] <= c2["open"]:
        return False

    # Engulfing body
    return (c2["open"] <= c1["close"]) and (c2["close"] >= c1["open"])


# ------------------------------
# Load All Screener Data
# ------------------------------
async def load_screener_data(symbol: str, interval: str = "1h"):
    data = {
        "close": None,
        "prev_close": None,
        "rsi": None,
        "macd": None,
        "signal": None,
        "hist": None,
        "ema20": None,
        "ema50": None,
        "ema200": None,
        "volume": None,
        "volume_ma": None,
        "candle_1": None,
        "candle_2": None,
        "avg_7d": None,
        "support": None,
        "resistance": None,
        "bullish_engulfing": False,
    }

    # ------------------------------
    # 1) TIME SERIES DATA (price + volume)
    # ------------------------------
    ts = await get_indicator(symbol, interval, "time_series", "&outputsize=60")

    if ts and "values" in ts:
        candles = ts["values"]

        if len(candles) >= 2:
            data["close"] = float(candles[0]["close"])
            data["prev_close"] = float(candles[1]["close"])

            data["volume"] = float(candles[0]["volume"])

            # Volume MA 20
            vols = [float(c["volume"]) for c in candles[:20]]
            data["volume_ma"] = sum(vols) / len(vols) if vols else None

            # Prepare candles for pattern detection
            data["candle_1"] = {
                "open": float(candles[1]["open"]),
                "close": float(candles[1]["close"])
            }
            data["candle_2"] = {
                "open": float(candles[0]["open"]),
                "close": float(candles[0]["close"])
            }

            # Detect bullish engulfing
            data["bullish_engulfing"] = is_bullish_engulfing(
                data["candle_1"], data["candle_2"]
            )

    # ------------------------------
    # 2) RSI
    # ------------------------------
    rsi_data = await get_indicator(symbol, interval, "rsi", "&time_period=14")
    if rsi_data and "values" in rsi_data:
        try:
            data["rsi"] = float(rsi_data["values"][0]["rsi"])
        except:
            pass

    # ------------------------------
    # 3) MACD
    # ------------------------------
    macd_data = await get_indicator(
        symbol, interval, "macd",
        "&fast_period=12&slow_period=26&signal_period=9"
    )
    if macd_data and "values" in macd_data:
        try:
            m = macd_data["values"][0]
            data["macd"] = float(m["macd"])
            data["signal"] = float(m["macd_signal"])
            data["hist"] = float(m["macd_hist"])
        except:
            pass

    # ------------------------------
    # 4) EMA20 / EMA50 / EMA200
    # ------------------------------
    ema20 = await get_indicator(symbol, interval, "ema", "&time_period=20")
    ema50 = await get_indicator(symbol, interval, "ema", "&time_period=50")
    ema200 = await get_indicator(symbol, interval, "ema", "&time_period=200")

    if ema20 and "values" in ema20:
        try:
            data["ema20"] = float(ema20["values"][0]["ema"])
        except:
            pass

    if ema50 and "values" in ema50:
        try:
            data["ema50"] = float(ema50["values"][0]["ema"])
        except:
            pass

    if ema200 and "values" in ema200:
        try:
            data["ema200"] = float(ema200["values"][0]["ema"])
        except:
            pass

    # ------------------------------
    # 5) LAST 7 DAILY CANDLES (for average + trendline logic)
    # ------------------------------
    daily_hist = await get_historical(symbol, "1day", 10)

    if daily_hist and len(daily_hist) >= 7:
        closes_7d = [float(c["close"]) for c in daily_hist[:7]]
        data["avg_7d"] = sum(closes_7d) / 7

    if daily_hist and len(daily_hist) >= 5:
        highs = [float(c["high"]) for c in daily_hist[:5]]
        lows = [float(c["low"]) for c in daily_hist[:5]]
        data["resistance"] = max(highs)
        data["support"] = min(lows)

    return data