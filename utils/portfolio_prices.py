import aiohttp
import asyncio
import time
from typing import List, Dict, Any
import os
from dotenv import load_dotenv

load_dotenv()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")


COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_IDS = {}  # UPPER_SYMBOL -> coin_id mapping
CACHE = {}          # symbol -> {price, change_pct, time}
CACHE_TTL = 120     # seconds


async def get_portfolio_crypto_prices(symbols) -> Dict[str, Dict[str, Any]]:

    if isinstance(symbols, str):
        symbols = [symbols]

    symbols = [s.upper().strip() for s in symbols if isinstance(s, str) and s.strip()]
    symbols = list(dict.fromkeys(symbols))  # remove duplicates

    now = time.time()
    output: Dict[str, Dict[str, Any]] = {}

    # Check cache
    missing = []
    for sym in symbols:
        c = CACHE.get(sym)
        if c and (now - c.get("time", 0) < CACHE_TTL):
            output[sym] = {
                "price": c.get("price"),
                "change_pct": c.get("change_pct")
            }
        else:
            missing.append(sym)

    if not missing:
        return output

    headers = {}
    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

    async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as session:
        for sym in missing:

            # Map symbol -> coin_id
            coin_id = COINGECKO_IDS.get(sym)
            if not coin_id:
                try:
                    search_url = f"https://api.coingecko.com/api/v3/search?query={sym.lower()}"
                    resp = await session.get(search_url)
                    data = await resp.json()
                    coins = data.get("coins", [])
                    if coins:
                        coin = next(
                            (c for c in coins if c["symbol"].lower() == sym.lower()),
                            coins[0]
                        )
                        coin_id = coin["id"]
                        COINGECKO_IDS[sym] = coin_id
                    else:
                        coin_id = None
                except Exception as e:
                    print(f"⚠️ Search error for {sym}: {e}")
                    coin_id = None

            if not coin_id:
                output[sym] = {"price": None, "change_pct": None}
                CACHE[sym] = {"price": None, "change_pct": None, "time": time.time()}
                continue

            # Fetch full coin data
            try:
                coin_url = (
                    f"https://api.coingecko.com/api/v3/coins/{coin_id}"
                    f"?localization=false&tickers=false&market_data=true"
                )
                resp = await session.get(coin_url)
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}")

                data = await resp.json()
                market = data.get("market_data", {})

                price_val = market.get("current_price", {}).get("usd")
                change_pct_val = market.get("price_change_percentage_24h")

                # Fallback 24h calculation
                if change_pct_val in (None, "", "null"):
                    try:
                        chart_url = (
                            f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
                            f"?vs_currency=usd&days=1"
                        )
                        chart_resp = await session.get(chart_url)

                        if chart_resp.status == 200:
                            chart_data = await chart_resp.json()
                            prices = chart_data.get("prices", [])
                            if len(prices) > 1:
                                old_price = prices[0][1]
                                new_price = prices[-1][1]
                                if old_price and new_price:
                                    change_pct_val = ((new_price - old_price) / old_price) * 100
                                else:
                                    change_pct_val = 0.0
                            else:
                                change_pct_val = 0.0
                        else:
                            change_pct_val = 0.0

                    except Exception as e:
                        print(f"⚠️ Fallback 24h change error for {sym}: {e}")
                        change_pct_val = 0.0

                # Type safety
                try:
                    price_val = float(price_val) if price_val is not None else None
                except:
                    price_val = None

                try:
                    change_pct_val = float(change_pct_val) if change_pct_val is not None else 0.0
                except:
                    change_pct_val = 0.0

                output[sym] = {"price": price_val, "change_pct": change_pct_val}
                CACHE[sym] = {"price": price_val, "change_pct": change_pct_val, "time": time.time()}

            except Exception as e:
                print(f"❌ Error fetching coin data for {sym}: {e}")
                output[sym] = {"price": None, "change_pct": None}
                CACHE[sym] = {"price": None, "change_pct": None, "time": time.time()}

    return output