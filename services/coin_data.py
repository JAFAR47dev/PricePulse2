#import os
#import requests
#from dotenv import load_dotenv

# Load API key from .env
#load_dotenv()
#COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")

#def get_coin_data(symbol):
#    """
#    Fetch detailed data for a cryptocurrency using the CoinGecko API.
#    Automatically includes API key from your .env file.
#    """

#    headers = {}
#    if COINGECKO_API_KEY:
#        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

#    # 🔍 Step 1: Search for the coin
#    search_url = f"https://api.coingecko.com/api/v3/search?query={symbol.lower()}"
#    search_resp = requests.get(search_url, headers=headers, timeout=10)

#    if search_resp.status_code != 200:
#        print(f"⚠️ Search failed ({search_resp.status_code}) for {symbol}")
#        return None

#    coins = search_resp.json().get("coins", [])
#    if not coins:
#        print(f"⚠️ No coins found for symbol: {symbol}")
#        return None

#    # ✅ Prefer exact symbol match
#    coin = next((c for c in coins if c["symbol"].lower() == symbol.lower()), coins[0])
#    coin_id = coin["id"]

#    # 📈 Step 2: Get full coin data
#    data_url = f"https://api.coingecko.com/api/v3/coins/{coin_id}?localization=false&tickers=false&market_data=true"
#    response = requests.get(data_url, headers=headers, timeout=10)

#    if response.status_code != 200:
#        print(f"❌ Failed to fetch data for {coin_id}: HTTP {response.status_code}")
#        return None

#    return response.json()
# 
       
import os
import json
import requests
from dotenv import load_dotenv

# Load API key
load_dotenv()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")

# Load your top 200 coin mapping file
with open("services/coingecko_ids.json", "r") as f:
    # Normalize keys to lowercase for safe lookup
    COINGECKO_IDS = {k.lower(): v for k, v in json.load(f).items()}


def get_coin_data(symbol: str):
    """
    Fetch full market data for a cryptocurrency using ONLY ONE API CALL.
    Uses local coingecko_ids.json to map symbol -> coin_id.
    Fully handles case-insensitive symbols and missing coins.
    """

    if not symbol:
        print("⚠️ No symbol provided")
        return None

    # Normalize symbol for lookup
    symbol_lower = symbol.lower()

    # ✅ Step 1: Resolve coin_id locally
    coin_id = COINGECKO_IDS.get(symbol_lower)
    if not coin_id:
        print(f"⚠️ No CoinGecko ID found for symbol: {symbol}")
        return None

    headers = {}
    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

    # ✅ Step 2: Single API request to fetch full coin data
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}?localization=false&tickers=false&market_data=true"

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"❌ Failed to fetch data for {coin_id}: {e}")
        return None

    data = resp.json()
    if not data or "market_data" not in data:
        print(f"⚠️ Incomplete data received for {coin_id}")
        return None

    return data