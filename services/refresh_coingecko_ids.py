import aiohttp
import asyncio
import json
import os
from datetime import datetime

COINGECKO_TOP_COINS_URL = "https://api.coingecko.com/api/v3/coins/markets"
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "coingecko_ids.json")


async def fetch_top_coins(limit=200):
    """
    Fetch top 'limit' coins from CoinGecko and return {symbol: id}.
    """
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": limit,
        "page": 1,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(COINGECKO_TOP_COINS_URL, params=params, timeout=15) as response:
                if response.status != 200:
                    print(f"⚠️ Failed to fetch top coins: HTTP {response.status}")
                    return None
                data = await response.json()
                return {coin["symbol"].upper(): coin["id"] for coin in data}

    except Exception as e:
        print(f"❌ Error fetching top coins: {e}")
        return None


async def refresh_coingecko_ids():
    """
    Refresh the coingecko_ids.json file with the top 200 coins.
    """
    print("🔄 Refreshing CoinGecko token IDs...")

    coins = await fetch_top_coins()
    if not coins:
        print("⚠️ Could not refresh tokens (API issue).")
        return

    try:
        with open(OUTPUT_FILE, "w") as f:
            json.dump(coins, f, indent=2)

        print(f"✅ Updated coingecko_ids.json with {len(coins)} coins — {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")

    except Exception as e:
        print(f"❌ Error writing to coingecko_ids.json: {e}")


# ✅ Manual test entry point (run once)
if __name__ == "__main__":
    asyncio.run(refresh_coingecko_ids())