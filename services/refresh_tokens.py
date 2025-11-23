import asyncio
import aiohttp
import json
import os
from datetime import datetime

async def refresh_top_tokens(context):
    """
    Fetch top 100 cryptocurrencies by market cap from CoinGecko
    and save to wfolder/data/top_tokens.json
    (Async version for Telegram Job Queue)
    """
    try:
        print("🔄 Refreshing top 100 tokens from CoinGecko...")

        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 100,
            "page": 1,
        }

        # --- Use aiohttp (async) ---
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=15) as resp:
                if resp.status != 200:
                    print(f"⚠️ CoinGecko returned status {resp.status}")
                    return  # no return value required
                data = await resp.json()

        if not data:
            print("⚠️ No data returned from CoinGecko.")
            return

        tokens = [
            {"id": coin.get("id"), "symbol": coin.get("symbol"), "name": coin.get("name")}
            for coin in data
            if coin.get("id")
        ]

        # Save to wfolder/data/
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)

        file_path = os.path.join(data_dir, "top_tokens.json")

        # Save asynchronously
        json_text = json.dumps(tokens, indent=2, ensure_ascii=False)
        await asyncio.to_thread(lambda: open(file_path, "w", encoding="utf-8").write(json_text))

        print(f"✅ Top 100 tokens refreshed successfully at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📦 Saved to: {file_path}")

    except Exception as e:
        print(f"❌ [refresh_top_tokens] Unexpected error: {e}")
        # No return needed