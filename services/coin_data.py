"""
Enhanced CoinGecko coin data service with market cap-based collision resolution
"""

import os
import json
import requests
import time
from dotenv import load_dotenv

load_dotenv()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")

COIN_LIST_CACHE = "services/coingecko_ids_all.json"
COLLISION_CACHE = "services/coingecko_collisions_resolved.json"
CACHE_TTL = 7 * 24 * 60 * 60  # 7 days


def _load_or_update_coin_list():
    """Load full coin list from CoinGecko API with caching"""
    # Use cache if fresh
    if os.path.exists(COIN_LIST_CACHE):
        age = time.time() - os.path.getmtime(COIN_LIST_CACHE)
        if age < CACHE_TTL:
            with open(COIN_LIST_CACHE, "r") as f:
                return json.load(f)

    headers = {}
    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

    url = "https://api.coingecko.com/api/v3/coins/list"
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print("❌ Failed to fetch CoinGecko coin list:", e)
        # Try to load stale cache as fallback
        if os.path.exists(COIN_LIST_CACHE):
            with open(COIN_LIST_CACHE, "r") as f:
                return json.load(f)
        return {}

    coins = resp.json()

    # Build symbol → [coin_ids] map
    mapping = {}
    for coin in coins:
        symbol = coin.get("symbol")
        coin_id = coin.get("id")
        name = coin.get("name")
        if symbol and coin_id:
            # Store both ID and name for better debugging
            mapping.setdefault(symbol.lower(), []).append({
                "id": coin_id,
                "name": name
            })

    os.makedirs(os.path.dirname(COIN_LIST_CACHE), exist_ok=True)
    with open(COIN_LIST_CACHE, "w") as f:
        json.dump(mapping, f, indent=2)

    print(f"✅ Updated coin list cache with {len(mapping)} symbols")
    return mapping


def _load_collision_cache():
    """Load cached collision resolutions"""
    if os.path.exists(COLLISION_CACHE):
        try:
            with open(COLLISION_CACHE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}


def _save_collision_cache(cache: dict):
    """Save collision resolutions to cache"""
    os.makedirs(os.path.dirname(COLLISION_CACHE), exist_ok=True)
    with open(COLLISION_CACHE, "w") as f:
        json.dump(cache, f, indent=2)


# Load mappings once at startup
COINGECKO_IDS = _load_or_update_coin_list()
COLLISION_RESOLUTION_CACHE = _load_collision_cache()


def _resolve_best_coin_id(symbol: str):
    """
    Resolve symbol collisions by choosing the coin with the highest market cap.
    Uses persistent caching to avoid repeated API calls.
    
    Args:
        symbol: Coin symbol (e.g., 'btc', 'eth')
    
    Returns:
        str: CoinGecko coin ID or None if not found
    """
    symbol_lower = symbol.lower()
    coin_entries = COINGECKO_IDS.get(symbol_lower)

    if not coin_entries:
        print(f"⚠️ Symbol '{symbol}' not found in CoinGecko database")
        return None

    # No collision - single coin for this symbol
    if len(coin_entries) == 1:
        return coin_entries[0]["id"]

    # Check collision cache first (valid for 7 days)
    if symbol_lower in COLLISION_RESOLUTION_CACHE:
        cached = COLLISION_RESOLUTION_CACHE[symbol_lower]
        cache_age = time.time() - cached.get("timestamp", 0)
        
        if cache_age < CACHE_TTL:
            print(f"✅ Using cached resolution for '{symbol}': {cached['coin_id']}")
            return cached["coin_id"]

    # Multiple coins with same symbol - resolve by market cap
    coin_ids = [entry["id"] for entry in coin_entries]
    print(f"⚠️ Symbol collision detected for '{symbol}': {len(coin_ids)} coins found")
    print(f"   Candidates: {', '.join([e['name'] for e in coin_entries])}")

    headers = {}
    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

    url = "https://api.coingecko.com/api/v3/coins/markets"

    try:
        resp = requests.get(
            url,
            headers=headers,
            params={
                "vs_currency": "usd",
                "ids": ",".join(coin_ids),
                "order": "market_cap_desc",
                "per_page": len(coin_ids),
                "page": 1,
                "sparkline": False,
                "price_change_percentage": "24h"
            },
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"⚠️ Failed to resolve collision for '{symbol}': {e}")
        # Fallback to first coin in list
        fallback_id = coin_ids[0]
        print(f"   Using fallback: {fallback_id}")
        return fallback_id

    markets = resp.json()
    
    if not markets:
        print(f"⚠️ No market data returned for '{symbol}' collision resolution")
        return coin_ids[0]

    # Filter out coins with null market cap
    valid_markets = [m for m in markets if m.get("market_cap") is not None]
    
    if not valid_markets:
        print(f"⚠️ No valid market cap data for '{symbol}' collision")
        return coin_ids[0]

    # Sort by market cap descending (highest first)
    valid_markets.sort(key=lambda x: x.get("market_cap", 0), reverse=True)
    
    # Highest market cap wins
    winner = valid_markets[0]
    winner_id = winner["id"]
    winner_name = winner["name"]
    winner_cap = winner.get("market_cap", 0)
    
    print(f"✅ Resolved '{symbol}' collision → {winner_name} (${winner_cap:,.0f} market cap)")
    
    # Cache the resolution
    COLLISION_RESOLUTION_CACHE[symbol_lower] = {
        "coin_id": winner_id,
        "name": winner_name,
        "market_cap": winner_cap,
        "timestamp": time.time(),
        "total_candidates": len(coin_ids)
    }
    _save_collision_cache(COLLISION_RESOLUTION_CACHE)
    
    return winner_id


def get_coin_data(symbol: str):
    """
    Fetch full market data for ANY CoinGecko-listed coin.
    Symbol collisions are automatically resolved by market cap dominance.
    
    Args:
        symbol: Coin symbol (case-insensitive, e.g., 'BTC', 'eth')
    
    Returns:
        dict: Full coin data from CoinGecko or None if not found
    """
    if not symbol:
        print("⚠️ No symbol provided to get_coin_data")
        return None

    coin_id = _resolve_best_coin_id(symbol)

    if not coin_id:
        print(f"⚠️ Symbol not found on CoinGecko: {symbol}")
        return None

    headers = {}
    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

    url = (
        f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        "?localization=false&tickers=false&market_data=true"
        "&community_data=false&developer_data=false"
    )

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"❌ Failed to fetch data for {coin_id}: {e}")
        return None

    data = resp.json()
    
    if "market_data" not in data:
        print(f"⚠️ Incomplete data for {coin_id}")
        return None

    return data


def clear_collision_cache():
    """
    Manually clear the collision resolution cache.
    Useful for debugging or forcing fresh resolutions.
    """
    global COLLISION_RESOLUTION_CACHE
    COLLISION_RESOLUTION_CACHE = {}
    if os.path.exists(COLLISION_CACHE):
        os.remove(COLLISION_CACHE)
    print("✅ Collision cache cleared")


def get_collision_stats():
    """
    Get statistics about symbol collisions.
    
    Returns:
        dict: Collision statistics
    """
    total_symbols = len(COINGECKO_IDS)
    collision_symbols = [s for s, coins in COINGECKO_IDS.items() if len(coins) > 1]
    num_collisions = len(collision_symbols)
    
    # Find worst offenders
    worst_collisions = sorted(
        [(s, len(coins)) for s, coins in COINGECKO_IDS.items()],
        key=lambda x: x[1],
        reverse=True
    )[:10]
    
    return {
        "total_symbols": total_symbols,
        "collision_count": num_collisions,
        "collision_percentage": (num_collisions / total_symbols * 100) if total_symbols > 0 else 0,
        "worst_collisions": worst_collisions,
        "resolved_count": len(COLLISION_RESOLUTION_CACHE)
    }


# Example usage and testing
if __name__ == "__main__":
    # Test collision resolution
    test_symbols = ["btc", "eth", "uni", "link", "cake"]
    
    print("Testing collision resolution...")
    for sym in test_symbols:
        print(f"\n{'='*50}")
        print(f"Testing: {sym.upper()}")
        print(f"{'='*50}")
        
        data = get_coin_data(sym)
        if data:
            print(f"✅ Resolved to: {data['name']} ({data['id']})")
            print(f"   Market Cap Rank: #{data.get('market_cap_rank', 'N/A')}")
        else:
            print(f"❌ Failed to resolve {sym}")
    
    # Show collision statistics
    print(f"\n{'='*50}")
    print("Collision Statistics")
    print(f"{'='*50}")
    stats = get_collision_stats()
    for key, value in stats.items():
        if key != "worst_collisions":
            print(f"{key}: {value}")
    
    print("\nWorst collision offenders:")
    for symbol, count in stats["worst_collisions"]:
        print(f"  {symbol.upper()}: {count} coins")