import requests
import os
from dotenv import load_dotenv

load_dotenv()
CRYPTOCOMPARE_API_KEY = os.getenv("CRYPTOCOMPARE_API_KEY")

        
def get_crypto_price(coin_id: str):
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()

        price = data.get(coin_id, {}).get("usd")
        if price is None:
            print(f"❌ No USD price found for {coin_id}. Full response: {data}")
        return price
    except Exception as e:
        print(f"❌ Error fetching price for {coin_id}: {e}")
        return None
        
def get_candles(symbol, limit=100):
    url = f"https://min-api.cryptocompare.com/data/histohour?fsym={symbol.upper()}&tsym=USD&limit={limit}"
    headers = {"authorization": f"Apikey {CRYPTOCOMPARE_API_KEY}"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        return [item["close"] for item in data.get("Data", [])]
    except Exception as e:
        print(f"Error fetching candles: {e}")
        return []

    if data is valid:
        count_api_call()
        return price

def calculate_ema(prices, period):
    if len(prices) < period:
        return None
    ema = prices[:period]
    multiplier = 2 / (period + 1)
    for price in prices[period:]:
        ema_val = (price - ema[-1]) * multiplier + ema[-1]
        ema.append(ema_val)
    return ema[-1]

def get_macd(symbol):
    prices = get_candles(symbol, 50)
    if len(prices) < 26:
        return None, None, None

    ema_12 = calculate_ema(prices, 12)
    ema_26 = calculate_ema(prices, 26)

    if ema_12 is None or ema_26 is None:
        return None, None, None

    macd = ema_12 - ema_26
    macd_line = [calculate_ema(prices[i:], 12) - calculate_ema(prices[i:], 26) for i in range(9)]
    signal_line = sum(macd_line) / len(macd_line)
    hist = macd - signal_line
    return macd, signal_line, hist