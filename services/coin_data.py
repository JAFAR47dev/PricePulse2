import os
import requests
from dotenv import load_dotenv

# Load API key from .env
load_dotenv()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")

def get_coin_data(symbol):
    """
    Fetch detailed data for a cryptocurrency using the CoinGecko API.
    Automatically includes API key from your .env file.
    """

    headers = {}
    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

    # 🔍 Step 1: Search for the coin
    search_url = f"https://api.coingecko.com/api/v3/search?query={symbol.lower()}"
    search_resp = requests.get(search_url, headers=headers, timeout=10)

    if search_resp.status_code != 200:
        print(f"⚠️ Search failed ({search_resp.status_code}) for {symbol}")
        return None

    coins = search_resp.json().get("coins", [])
    if not coins:
        print(f"⚠️ No coins found for symbol: {symbol}")
        return None

    # ✅ Prefer exact symbol match
    coin = next((c for c in coins if c["symbol"].lower() == symbol.lower()), coins[0])
    coin_id = coin["id"]

    # 📈 Step 2: Get full coin data
    data_url = f"https://api.coingecko.com/api/v3/coins/{coin_id}?localization=false&tickers=false&market_data=true"
    response = requests.get(data_url, headers=headers, timeout=10)

    if response.status_code != 200:
        print(f"❌ Failed to fetch data for {coin_id}: HTTP {response.status_code}")
        return None

    return response.json()