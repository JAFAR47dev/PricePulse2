import aiohttp
import json
import os
import asyncio
import time
from dotenv import load_dotenv

# === Load environment variables ===
load_dotenv()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3/simple/price"

# === Load symbol-to-id mapping once ===
base_dir = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(base_dir, "coingecko_ids.json")

with open(file_path, "r") as f:
    COINGECKO_IDS = json.load(f)

# === Caching setup ===
CACHE = {}
CACHE_TTL = 60  # seconds


async def get_crypto_prices(symbols):
    """
    Fetch multiple crypto prices using CoinGecko API with caching and retry delay.
    Returns a dict like { "BTC": 67000.5, "ETH": 3200.8 }.
    """
    if isinstance(symbols, str):
        symbols = [symbols]

    # Normalize symbols
    symbols = [s.upper() for s in symbols]

    # Check cache first
    now = time.time()
    cached_prices = {}
    missing_symbols = []

    for sym in symbols:
        cached_entry = CACHE.get(sym)
        if cached_entry and now - cached_entry["time"] < CACHE_TTL:
            cached_prices[sym] = cached_entry["price"]
        else:
            missing_symbols.append(sym)

    # If all are cached, return immediately
    if not missing_symbols:
        return cached_prices

    # Map missing symbols to CoinGecko IDs
    ids = []
    symbol_to_id = {}
    for sym in missing_symbols:
        coin_id = COINGECKO_IDS.get(sym)
        if coin_id:
            ids.append(coin_id)
            symbol_to_id[coin_id] = sym

    if not ids:
        print("⚠️ No valid CoinGecko IDs found for given symbols.")
        return cached_prices

    # Build API request
    url = f"{COINGECKO_BASE_URL}?ids={','.join(ids)}&vs_currencies=usd"
    headers = {}
    if COINGECKO_API_KEY:
        headers["x-cg-pro-api-key"] = COINGECKO_API_KEY

    try:
        async with aiohttp.ClientSession() as session:
            for attempt in range(3):  # up to 3 retries
                async with session.get(url, headers=headers, timeout=10) as response:
                    if response.status == 429:
                        wait = 2 ** attempt  # exponential backoff (2s, 4s, 8s)
                        print(f"⚠️ Rate limit hit. Retrying in {wait}s...")
                        await asyncio.sleep(wait)
                        continue
                    elif response.status != 200:
                        text = await response.text()
                        print(f"❌ HTTP error {response.status}: {text}")
                        return cached_prices

                    data = await response.json()

                    # Update cache
                    for coin_id, content in data.items():
                        usd_price = content.get("usd")
                        if usd_price is not None:
                            sym = symbol_to_id[coin_id]
                            CACHE[sym] = {"price": float(usd_price), "time": time.time()}
                            cached_prices[sym] = float(usd_price)

                    return cached_prices

    except Exception as e:
        print(f"❌ Error fetching crypto prices: {e}")
        return cached_prices
