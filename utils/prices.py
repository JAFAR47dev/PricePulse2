import aiohttp
import asyncio
import json
import os

BINANCE_BASE_URL = "https://api.binance.com/api/v3/ticker/price"
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3/simple/price"

# Get directory of this script (prices.py)
base_dir = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(base_dir, "coingecko_ids.json")

# Load symbol-to-id mapping once
with open(file_path, "r") as f:
    COINGECKO_IDS = json.load(f)

async def fetch_price_binance(session, symbol):
    url = f"{BINANCE_BASE_URL}?symbol={symbol}"
    try:
        async with session.get(url, timeout=10) as response:
            data = await response.json()
            return float(data['price'])
    except Exception as e:
        print(f"❌ Binance error for {symbol}: {e}")
        return None

async def fetch_price_coingecko(session, symbol):
    # Convert 'BTCUSDT' → 'BTC' and 'usd'
    if symbol.endswith("USDT"):
        coin_symbol = symbol[:-4]
        currency = "usd"
    elif symbol.endswith("BTC"):
        coin_symbol = symbol[:-3]
        currency = "btc"
    else:
        coin_symbol = symbol
        currency = "usd"

    coin_id = COINGECKO_IDS.get(coin_symbol.upper())
    if not coin_id:
        print(f"❌ Unknown symbol in coingecko_ids: {coin_symbol.upper()}")
        return None

    url = f"{COINGECKO_BASE_URL}?ids={coin_id}&vs_currencies={currency}"
    try:
        async with session.get(url, timeout=10) as response:
            data = await response.json()
            if not data:
                print(f"❌ No price data for {coin_symbol.upper()} from CoinGecko. Full response: {data}")
                return None
            price = data.get(coin_id, {}).get(currency)
            if price is None:
                print(f"❌ Missing '{currency}' price for {coin_id} in CoinGecko response: {data}")
            return float(price) if price else None
    except Exception as e:
        print(f"❌ Error fetching price for {coin_symbol.upper()} from CoinGecko: {e}")
        return None

async def fetch_price(session, symbol):
    price = await fetch_price_binance(session, symbol)
    if price is not None:
        return symbol, price

    print(f"⚠️ Binance unavailable for {symbol}. Trying CoinGecko...")
    price = await fetch_price_coingecko(session, symbol)
    return symbol, price

async def get_crypto_prices(symbols):
    result = {}
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_price(session, symbol) for symbol in symbols]
        responses = await asyncio.gather(*tasks)

        for symbol, price in responses:
            result[symbol] = price
    return result