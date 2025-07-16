import httpx
from config import TWELVE_DATA_API_KEY
import asyncio

TIMEFRAME_MAP = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "8h": "8h",
    "1d": "1day"
}


async def fetch_candles(symbol: str, tf: str = "1h", limit: int = 2000):
    if tf not in TIMEFRAME_MAP:
        print("Invalid timeframe:", tf)
        return None

    interval = TIMEFRAME_MAP[tf]
    formatted_symbol = f"{symbol.upper().replace('USDT', '')}/USD"
    base_url = "https://api.twelvedata.com"

    params = {
        "symbol": formatted_symbol,
        "interval": interval,
        "outputsize": limit,
        "apikey": TWELVE_DATA_API_KEY
    }

    async with httpx.AsyncClient() as client:
        try:
            # Fetch candles + indicators
            candle_req = client.get(f"{base_url}/time_series", params=params)
            rsi_req = client.get(f"{base_url}/rsi", params=params)
            ema20_req = client.get(f"{base_url}/ema", params={**params, "time_period": 20})
            ema50_req = client.get(f"{base_url}/ema", params={**params, "time_period": 50})
            ema200_req = client.get(f"{base_url}/ema", params={**params, "time_period": 200})
            macd_req = client.get(f"{base_url}/macd", params=params)

            (
                candle_res,
                rsi_res,
                ema20_res,
                ema50_res,
                ema200_res,
                macd_res
            ) = await asyncio.gather(
                candle_req,
                rsi_req,
                ema20_req,
                ema50_req,
                ema200_req,
                macd_req
            )

            candles = candle_res.json().get("values", [])
            rsi_data = {i["datetime"]: i for i in rsi_res.json().get("values", [])}
            ema20_data = {i["datetime"]: i for i in ema20_res.json().get("values", [])}
            ema50_data = {i["datetime"]: i for i in ema50_res.json().get("values", [])}
            ema200_data = {i["datetime"]: i for i in ema200_res.json().get("values", [])}
            macd_data = {i["datetime"]: i for i in macd_res.json().get("values", [])}

            for candle in candles:
                dt = candle["datetime"]
                candle["rsi"] = float(rsi_data.get(dt, {}).get("rsi", 0))
                candle["ema"] = float(ema20_data.get(dt, {}).get("ema", 0))
                candle["ema50"] = float(ema50_data.get(dt, {}).get("ema", 0))
                candle["ema200"] = float(ema200_data.get(dt, {}).get("ema", 0))
                candle["macd"] = float(macd_data.get(dt, {}).get("macd", 0))
                candle["macdSignal"] = float(macd_data.get(dt, {}).get("macd_signal", 0))
                candle["macdHist"] = float(macd_data.get(dt, {}).get("macd_hist", 0))
                candle["close"] = float(candle["close"])  # Ensure type

            return candles

        except Exception as e:
            print("❌ Candle or indicator fetch failed:", e)
            return None