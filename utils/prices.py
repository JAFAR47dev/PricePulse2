import aiohttp
import asyncio
import json
import os


async def fetch_price_coingecko(session, symbol):
    # Convert something like 'BTCUSDT' → coin_symbol: 'BTC', currency: 'USD'
    if symbol.endswith("USDT"):
        coin_symbol = symbol[:-4]
        currency = "usd"
    elif symbol.endswith("BTC"):
        coin_symbol = symbol[:-3]
        currency = "btc"
    else:
        coin_symbol = symbol  # fallback
        currency = "usd"

    coin_id = COINGECKO_IDS.get(coin_symbol.upper())
    if not coin_id:
        return None  # unknown coin

    url = f"{COINGECKO_BASE_URL}?ids={coin_id}&vs_currencies={currency}"
    try:
        async with session.get(url, timeout=10) as response:
            data = await response.json()
            return float(data.get(coin_id, {}).get(currency))
    except:
        return None

async def fetch_price(session, symbol):
    # Try Binance first
    price = await fetch_price_binance(session, symbol)
    if price is not None:
        return symbol, price

    # Fallback to CoinGecko
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