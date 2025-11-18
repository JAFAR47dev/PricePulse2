import requests
import json
import os
from datetime import datetime

def refresh_top_tokens():
    """
    Fetch top 100 cryptocurrencies by market cap from CoinGecko
    and save to wfolder/data/top_tokens.json
    """
    print("🔄 Refreshing top 100 tokens from CoinGecko...")

    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 100,
        "page": 1,
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        if not data:
            print("⚠️ No data returned from CoinGecko.")
            return False

        tokens = [
            {"id": coin["id"], "symbol": coin["symbol"], "name": coin["name"]}
            for coin in data
        ]

        # ✅ Save inside wfolder/data/
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)

        file_path = os.path.join(data_dir, "top_tokens.json")

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(tokens, f, indent=2, ensure_ascii=False)

        print(f"✅ Top 100 tokens refreshed successfully at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📦 Saved to: {file_path}")
        return True

    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to refresh tokens: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


if __name__ == "__main__":
    refresh_top_tokens()