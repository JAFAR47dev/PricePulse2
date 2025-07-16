import requests
import json

def fetch_top_100_coins():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 100,
        "page": 1,
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    top_coins = [
        {"id": coin["id"], "symbol": coin["symbol"].lower(), "name": coin["name"]}
        for coin in response.json()
    ]

    # Write the result to a JSON file in the same folder
    with open("top_100_coins.json", "w") as f:
        json.dump(top_coins, f, indent=2)

# Run the function when the script is executed directly
if __name__ == "__main__":
    fetch_top_100_coins()