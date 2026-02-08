import os
import json
import asyncio
from datetime import datetime
import aiohttp
from dotenv import load_dotenv

# Load environment
load_dotenv()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")

# Constants
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "top100_coingecko_ids.json")
COINGECKO_TOP_COINS_URL = "https://api.coingecko.com/api/v3/coins/markets"


async def fetch_top_coins(limit=100):
    """
    Fetch top 'limit' coins from CoinGecko (default 100) and return {symbol: id}.
    Uses API key for higher rate limits if available.
    """

    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": limit,  # 100 coins in one request
        "page": 1,
        "sparkline": "false",
    }

    headers = {}
    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.get(COINGECKO_TOP_COINS_URL, params=params, headers=headers) as response:
                if response.status != 200:
                    print(f"⚠️ Failed to fetch top coins: HTTP {response.status}")
                    return None

                data = await response.json()
                # Return symbol (uppercase) -> coin_id mapping
                return {coin["symbol"].upper(): coin["id"] for coin in data}

    except Exception as e:
        print(f"❌ Error fetching top coins: {e}")
        return None


async def refresh_top100_coingecko_ids(context=None):
    """
    Refresh the coingecko_ids_top100.json file with the top 100 coins.
    """
    print("🔄 Refreshing CoinGecko token IDs (Top 100)...")

    coins = await fetch_top_coins(limit=100)
    if not coins:
        print("⚠️ Could not refresh tokens (API issue).")
        return

    try:
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        with open(OUTPUT_FILE, "w") as f:
            json.dump(coins, f, indent=2)

        print(f"✅ Updated coingecko_ids_top100.json with {len(coins)} coins — {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")

    except Exception as e:
        print(f"❌ Error writing to coingecko_ids_top100.json: {e}")


# ✅ Manual test entry point
if __name__ == "__main__":
    asyncio.run(refresh_coingecko_ids())