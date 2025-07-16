# utils/update_ids.py

import requests
import json
import os

def fetch_top_200_ids():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 200,
        "page": 1
    }

    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    # Create symbol-to-id mapping (e.g., 'BTC': 'bitcoin')
    mapping = {coin["symbol"].upper(): coin["id"] for coin in data}
    return mapping

def save_ids_to_file(mapping):
    # Ensure the utils folder path works from any location
    base_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_dir, "coingecko_ids.json")

    with open(file_path, "w") as f:
        json.dump(mapping, f, indent=2)
    print(f"✅ Saved {len(mapping)} coin IDs to {file_path}")

if __name__ == "__main__":
    try:
        ids = fetch_top_200_ids()
        save_ids_to_file(ids)
    except Exception as e:
        print("❌ Failed to update CoinGecko IDs:", e)