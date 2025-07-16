import os
import json
import time
import requests

COINDAR_API_KEY = os.getenv("COINDAR_API_KEY")
CACHE_FILE = os.path.join(os.path.dirname(__file__), "coin_map_cache.json")
CACHE_DURATION = 86400  # 24 hours in seconds

def fetch_coin_map_from_api():
    url = "https://coindar.org/api/v2/coins"
    params = {"access_token": COINDAR_API_KEY}
    r = requests.get(url, params=params)
    r.raise_for_status()

    coin_map = {}
    for coin in r.json():
        coin_map[str(coin["id"])] = {
            "name": coin.get("name", "Unknown"),
            "symbol": coin.get("symbol", "").upper()
        }

    return coin_map

def load_coin_map():
    # Load from cache if fresh
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)
            if time.time() - data.get("timestamp", 0) < CACHE_DURATION:
                return data["coin_map"]

    # Otherwise, fetch new data and cache it
    coin_map = fetch_coin_map_from_api()
    with open(CACHE_FILE, "w") as f:
        json.dump({
            "timestamp": time.time(),
            "coin_map": coin_map
        }, f)

    return coin_map