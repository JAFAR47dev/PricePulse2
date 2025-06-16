import requests

def get_coin_data(symbol):
    # Use CoinGecko search to find the best match
    search_url = f"https://api.coingecko.com/api/v3/search?query={symbol.lower()}"
    search_resp = requests.get(search_url).json()
    coins = search_resp.get("coins", [])

    # Find a matching symbol, preferring exact match
    coin = next((c for c in coins if c["symbol"].lower() == symbol.lower()), None)

    if not coin:
        return None

    coin_id = coin["id"]
    data_url = f"https://api.coingecko.com/api/v3/coins/{coin_id}?localization=false&tickers=false&market_data=true"
    response = requests.get(data_url)

    if response.status_code != 200:
        return None

    return response.json()