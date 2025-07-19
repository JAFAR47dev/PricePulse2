import httpx
import asyncio
from config import TWELVE_DATA_API_KEY


# Map user-friendly to API-valid
timeframe_map = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "8h": "8h",
    "1d": "1day",
    "1w": "1week"
    }

async def get_crypto_indicators(symbol: str, timeframe: str = "1h"):
    if not TWELVE_DATA_API_KEY:
        print("❌ TWELVE_DATA_API_KEY not set.")
        return None

    if timeframe not in timeframe_map:
        print(f"❌ Invalid timeframe: {timeframe}")
        return None

    symbol = symbol.upper().replace("USDT", "").replace("/", "")
    symbol = f"{symbol}/USD"
    print(f"📊 Final symbol for API: {symbol}")

    base_url = "https://api.twelvedata.com"
    params = {"symbol": symbol, "interval": timeframe, "apikey": TWELVE_DATA_API_KEY}

    async with httpx.AsyncClient() as client:
        try:
            # Indicator requests
            rsi_req = client.get(f"{base_url}/rsi", params=params)
            ema_req = client.get(f"{base_url}/ema", params={**params, "time_period": 20})
            macd_req = client.get(f"{base_url}/macd", params=params)
            price_req = client.get(f"{base_url}/price", params=params)
            candles_req = client.get(f"{base_url}/time_series", params={**params, "outputsize": 24})

            rsi_resp, ema_resp, macd_resp, price_resp, candles_resp = await asyncio.gather(
                rsi_req, ema_req, macd_req, price_req, candles_req
            )

            # Parse JSON
            rsi_data = rsi_resp.json()
            ema_data = ema_resp.json()
            macd_data = macd_resp.json()
            price_data = price_resp.json()
            candles_data = candles_resp.json()

            print("📉 RSI:", rsi_data)
            print("📉 EMA:", ema_data)
            print("📉 MACD:", macd_data)
            print("📉 Price:", price_data)
            print("📊 Candles:", candles_data)

            if (
                "values" not in rsi_data or
                "values" not in ema_data or
                "values" not in macd_data or
                "price" not in price_data or
                "values" not in candles_data
            ):
                print("❌ One or more required fields are missing.")
                return None

            # Parse indicators
            rsi_value = float(rsi_data["values"][0]["rsi"])
            ema_value = float(ema_data["values"][0]["ema"])
            macd_value = float(macd_data["values"][0]["macd"])
            macd_signal = float(macd_data["values"][0]["macd_signal"])
            macd_hist = float(macd_data["values"][0]["macd_hist"])
            price_value = float(price_data["price"])

            # Extract 24h stats from candles
            highs = [float(c["high"]) for c in candles_data["values"]]
            lows = [float(c["low"]) for c in candles_data["values"]]

            # Use 0 if volume is missing
            volumes = [float(c["volume"]) for c in candles_data["values"] if "volume" in c]

            high_24h = max(highs)
            low_24h = min(lows)
            total_volume = sum(volumes) if volumes else None

            return {
                "rsi": rsi_value,
                "ema20": ema_value,
                "macd": macd_value,
                "macdSignal": macd_signal,
                "macdHist": macd_hist,
                "price": price_value,
                "high_24h": high_24h,
                "low_24h": low_24h,
                "volume": total_volume
            }

        except Exception as e:
            print(f"❌ Indicator fetch failed: {e}")
            return None
            
import requests

async def get_volume_comparison(symbol: str, timeframe: str):
    """
    Returns current and average volume for a given symbol and timeframe.
    """

    # You can use Binance API as an example
    symbol = symbol.upper()
    tf_map = {
        "1h": "1h",
        "4h": "4h",
        "1d": "1d",
        "15m": "15m",
        "30m": "30m",
    }

    if timeframe not in tf_map:
        raise ValueError("Invalid timeframe")

    interval = tf_map[timeframe]
    limit = 50  # how many candles to fetch for average

    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"

    response = requests.get(url)
    if response.status_code != 200:
        raise Exception("Failed to fetch volume data")

    data = response.json()

    volumes = [float(kline[5]) for kline in data]  # 5th index = volume
    if not volumes:
        raise Exception("No volume data found")

    current_volume = volumes[-1]
    average_volume = sum(volumes[:-1]) / (len(volumes) - 1)  # exclude current candle for average

    return current_volume, average_volume
    
import aiohttp
import os
import time

from dotenv import load_dotenv
load_dotenv()

TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY")

# Cache dictionary: _cache[symbol][indicator_name] = {"value": ..., "timestamp": ...}
_indicator_cache = {}
CACHE_TTL = 60  # seconds


def is_fresh(entry):
    return time.time() - entry["timestamp"] < CACHE_TTL


# === GET RSI ===
async def get_cached_rsi(symbol):
    symbol = symbol.upper()
    if symbol in _indicator_cache and "rsi" in _indicator_cache[symbol]:
        if is_fresh(_indicator_cache[symbol]["rsi"]):
            return _indicator_cache[symbol]["rsi"]["value"]

    url = (
        f"https://api.twelvedata.com/rsi?symbol={symbol}/USDT&interval=1h"
        f"&apikey={TWELVE_DATA_API_KEY}&time_period=14"
    )

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            value = float(data.get("values", [{}])[0].get("rsi", 0))

            if symbol not in _indicator_cache:
                _indicator_cache[symbol] = {}
            _indicator_cache[symbol]["rsi"] = {"value": value, "timestamp": time.time()}
            return value


# === GET MACD ===
async def get_cached_macd(symbol):
    symbol = symbol.upper()
    if symbol in _indicator_cache and "macd" in _indicator_cache[symbol]:
        if is_fresh(_indicator_cache[symbol]["macd"]):
            return _indicator_cache[symbol]["macd"]["value"]

    url = (
        f"https://api.twelvedata.com/macd?symbol={symbol}/USDT&interval=1h"
        f"&apikey={TWELVE_DATA_API_KEY}&short_period=12&long_period=26&signal_period=9"
    )

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            val = data.get("values", [{}])[0]
            macd = float(val.get("macd", 0))
            signal = float(val.get("macd_signal", 0))
            hist = float(val.get("macd_histogram", 0))

            if symbol not in _indicator_cache:
                _indicator_cache[symbol] = {}
            _indicator_cache[symbol]["macd"] = {
                "value": (macd, signal, hist),
                "timestamp": time.time()
            }
            return macd, signal, hist


# === GET EMA ===
async def get_cached_ema(symbol, period=20):
    symbol = symbol.upper()
    key = f"ema{period}"

    if symbol in _indicator_cache and key in _indicator_cache[symbol]:
        if is_fresh(_indicator_cache[symbol][key]):
            return _indicator_cache[symbol][key]["value"]

    url = (
        f"https://api.twelvedata.com/ema?symbol={symbol}/USDT&interval=1h"
        f"&time_period={period}&apikey={TWELVE_DATA_API_KEY}"
    )

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            ema = float(data.get("values", [{}])[0].get("ema", 0))

            if symbol not in _indicator_cache:
                _indicator_cache[symbol] = {}
            _indicator_cache[symbol][key] = {
                "value": ema,
                "timestamp": time.time()
            }
            return ema