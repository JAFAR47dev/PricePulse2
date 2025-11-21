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
CACHE_TTL = 90 # seconds


async def get_crypto_prices(symbols):
    """
    Fetch multiple crypto prices using CoinGecko API with caching and retry delay.
    OUTPUT FORMAT (always consistent):
    {
        "BTC": { "price": 67000, "change_pct": -1.3 },
        "ETH": { "price": 3500, "change_pct": 2.5 }
    }
    """
    if isinstance(symbols, str):
        symbols = [symbols]

    symbols = [s.upper() for s in symbols]
    now = time.time()
    cached = {}
    missing = []

    # Check cache
    for sym in symbols:
        c = CACHE.get(sym)
        if c and now - c["time"] < CACHE_TTL:
            cached[sym] = {"price": c["price"], "change_pct": c.get("change_pct")}
        else:
            missing.append(sym)

    # If all cached, return immediately
    if not missing:
        return cached

    # Map missing symbols to CoinGecko IDs
    ids = []
    sym_to_id = {}
    for sym in missing:
        coin_id = COINGECKO_IDS.get(sym)
        if coin_id:
            ids.append(coin_id)
            sym_to_id[coin_id] = sym

    if not ids:
        print("⚠️ No valid CoinGecko IDs for:", missing)
        for sym in missing:
            cached[sym] = {"price": None, "change_pct": None}
        return cached

    # Build request URL
    url = (
        f"{COINGECKO_BASE_URL}"
        f"?ids={','.join(ids)}"
        f"&vs_currencies=usd"
        f"&include_24hr_change=true"
    )
    headers = {}
    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

    output = {}

    try:
        async with aiohttp.ClientSession() as session:
            for attempt in range(3):
                async with session.get(url, headers=headers, timeout=10) as resp:
                    if resp.status == 429:
                        wait = 2 ** attempt
                        print(f"⚠️ Rate limit hit. Retrying in {wait}s...")
                        await asyncio.sleep(wait)
                        continue

                    if resp.status != 200:
                        text = await resp.text()
                        print(f"❌ HTTP {resp.status}: {text}")
                        # fallback to cached
                        for sym in symbols:
                            output[sym] = cached.get(sym, {"price": None, "change_pct": None})
                        return output

                    data = await resp.json()

                    # Parse API results
                    for coin_id, content in data.items():
                        sym = sym_to_id[coin_id]
                        price = content.get("usd")
                        change_pct = content.get("usd_24h_change")

                        if price is not None:
                            price = float(price)
                            CACHE[sym] = {"price": price, "change_pct": float(change_pct) if change_pct is not None else None, "time": time.time()}

                        output[sym] = {
                            "price": price,
                            "change_pct": float(change_pct) if change_pct is not None else None
                        }

                    # Include previously cached symbols not in this fetch
                    for sym in cached:
                        if sym not in output:
                            output[sym] = cached[sym]

                    return output

    except Exception as e:
        print("❌ Error fetching crypto prices:", e)
        # fallback to cached
        fallback = {}
        for sym in symbols:
            c = CACHE.get(sym)
            fallback[sym] = {
                "price": c["price"] if c else None,
                "change_pct": c.get("change_pct") if c else None
            }
        return fallback        