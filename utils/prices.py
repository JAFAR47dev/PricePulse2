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
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY  

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
        

async def get_portfolio_crypto_prices(symbols):
    """
    Safe multi-price fetcher for portfolio tools.
    ALWAYS RETURNS A CONSISTENT FORMAT:
    {
        "BTC": { "price": float|None, "change_pct": float|None },
        ...
    }
    """

    # Normalize input
    if isinstance(symbols, str):
        symbols = [symbols]
    symbols = [s.upper().strip() for s in symbols if isinstance(s, str)]

    now = time.time()
    cached = {}
    missing = []

    # ------- CHECK CACHE -------
    for sym in symbols:
        c = CACHE.get(sym)
        if c and now - c.get("time", 0) < CACHE_TTL:
            cached[sym] = {
                "price": c.get("price"),
                "change_pct": c.get("change_pct")
            }
        else:
            missing.append(sym)

    # If all symbols cached → return immediately
    if not missing:
        return {sym: cached[sym] for sym in symbols}

    # ------- MAP SYMBOLS TO COINGECKO IDs -------
    ids = []
    sym_to_id = {}

    for sym in missing:
        coin_id = COINGECKO_IDS.get(sym)
        if coin_id:
            ids.append(coin_id)
            sym_to_id[coin_id] = sym

    # If none of the missing symbols have IDs → return cached + placeholder
    if not ids:
        output = {}
        for sym in symbols:
            output[sym] = cached.get(sym, {"price": None, "change_pct": None})
        return output

    # ------- BUILD API URL -------
    url = (
        f"{COINGECKO_BASE_URL}"
        f"?ids={','.join(ids)}"
        f"&vs_currencies=usd"
        f"&include_24hr_change=true"
    )

    headers = {}
    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

    # Output dictionary
    output = {}

    # ------- FETCH WITH RETRIES -------
    try:
        async with aiohttp.ClientSession() as session:
            for attempt in range(3):

                try:
                    async with session.get(url, headers=headers, timeout=10) as resp:
                        status = resp.status

                        # Rate limit
                        if status == 429:
                            wait = 2 ** attempt
                            print(f"⚠️ Rate-limited. Retrying in {wait}s...")
                            await asyncio.sleep(wait)
                            continue

                        # Other non-200 error
                        if status != 200:
                            txt = await resp.text()
                            print(f"❌ HTTP {status}: {txt}")
                            raise Exception(f"HTTP {status}")

                        data = await resp.json()

                except asyncio.TimeoutError:
                    print("⏳ Timeout from CoinGecko, retrying...")
                    await asyncio.sleep(1)
                    continue
                except Exception as e:
                    print(f"❌ API error: {e}")
                    await asyncio.sleep(1)
                    continue

                # ---------- PARSE API RESPONSE SAFELY ----------
                for coin_id in ids:
                    sym = sym_to_id.get(coin_id)

                    content = data.get(coin_id, {}) if isinstance(data, dict) else {}

                    price = content.get("usd")
                    change_pct = content.get("usd_24h_change")

                    # Normalize values
                    price = float(price) if price not in [None, ""] else None
                    change_pct = float(change_pct) if change_pct not in [None, ""] else None

                    # Update cache
                    CACHE[sym] = {
                        "price": price,
                        "change_pct": change_pct,
                        "time": time.time()
                    }

                    output[sym] = {
                        "price": price,
                        "change_pct": change_pct
                    }

                break  # success → break retry loop

            else:
                # All retries failed → fallback
                raise Exception("All retries failed.")

    except Exception as e:
        print("❌ FINAL ERROR:", e)
        # Fallback to cached only
        for sym in symbols:
            c = CACHE.get(sym)
            output[sym] = {
                "price": c.get("price") if c else None,
                "change_pct": c.get("change_pct") if c else None
            }

        return output

    # ------- MERGE CACHED VALUES FOR SYMBOLS NOT UPDATED -------
    for sym in symbols:
        if sym not in output:
            output[sym] = cached.get(sym, {"price": None, "change_pct": None})

    return output  