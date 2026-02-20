import os
import json
import httpx
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# ✅ Load API keys
load_dotenv()

ETHPLORER_API_KEY = os.getenv("ETHPLORER_API_KEY", "freekey")
ETHPLORER_BASE = "https://api.ethplorer.io"

TOP_TOKENS_FILE = "services/top100_coingecko_ids.json"
WHALE_DATA_DIR = "whales/data"
os.makedirs(WHALE_DATA_DIR, exist_ok=True)

COINGECKO_BASE = "https://api.coingecko.com/api/v3"

# ✅ New cache and progress files
CONTRACT_CACHE_FILE = "whales/contract_cache.json"
PROGRESS_FILE = "whales/last_progress.json"

# Load or initialize caches
if os.path.exists(CONTRACT_CACHE_FILE):
    with open(CONTRACT_CACHE_FILE, "r") as f:
        CONTRACT_CACHE = json.load(f)
else:
    CONTRACT_CACHE = {}

if os.path.exists(PROGRESS_FILE):
    with open(PROGRESS_FILE, "r") as f:
        LAST_PROGRESS = json.load(f)
else:
    LAST_PROGRESS = {"last_completed": None}


# ✅ Helper: Save contract cache and progress
def save_cache_and_progress():
    with open(CONTRACT_CACHE_FILE, "w") as f:
        json.dump(CONTRACT_CACHE, f, indent=2)
    with open(PROGRESS_FILE, "w") as f:
        json.dump(LAST_PROGRESS, f, indent=2)


# ✅ Helper: Normalize the JSON file into a list of dicts
# This handles both formats safely:
#   Format A (dict):  {"BTC": "bitcoin", "ETH": "ethereum"}
#   Format B (list):  [{"symbol": "BTC", "id": "bitcoin"}, ...]
def load_tokens_as_list(filepath: str) -> list:
    """
    Load top tokens file and always return a consistent list format:
    [{"symbol": "BTC", "id": "bitcoin"}, {"symbol": "ETH", "id": "ethereum"}, ...]
    """
    with open(filepath, "r") as f:
        data = json.load(f)

    # Already a list of dicts — use directly
    if isinstance(data, list):
        return data

    # It's a flat dict like {"BTC": "bitcoin", ...} — convert it
    if isinstance(data, dict):
        return [{"symbol": symbol, "id": cg_id} for symbol, cg_id in data.items()]

    raise ValueError(f"Unexpected format in {filepath}: expected dict or list, got {type(data)}")


# ✅ Helper: Fetch ERC20 contract address from CoinGecko (with cache)
async def get_contract_address(token_id: str, symbol: str) -> str:
    """Fetch Ethereum contract address for a given token ID from CoinGecko, using cache"""
    # ✅ Check cache first
    if symbol in CONTRACT_CACHE:
        return CONTRACT_CACHE[symbol]

    url = f"{COINGECKO_BASE}/coins/{token_id}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        for attempt in range(3):
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    contract = data.get("platforms", {}).get("ethereum")
                    if contract:
                        CONTRACT_CACHE[symbol] = contract
                        save_cache_and_progress()
                    return contract
                elif resp.status_code == 429:
                    await asyncio.sleep(2 * (attempt + 1))
                else:
                    print(f"⚠️ CoinGecko error {resp.status_code} for {token_id}")
                    return None
            except Exception as e:
                print(f"⚠️ CoinGecko request error for {token_id}: {e}")
                await asyncio.sleep(2)
    return None


# ✅ Helper: Fetch top token holders (Ethplorer)
async def fetch_top_holders_ethplorer(contract_address: str, symbol: str, limit: int = 100):
    url = f"{ETHPLORER_BASE}/getTopTokenHolders/{contract_address}?apiKey={ETHPLORER_API_KEY}&limit={limit}"

    async with httpx.AsyncClient(timeout=25.0) as client:
        for attempt in range(3):
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    holders = data.get("holders", [])
                    if not holders:
                        print(f"⚠️ No Ethplorer whale data for {symbol}")
                        return []

                    whales = []
                    for rank, holder in enumerate(holders[:limit], start=1):
                        whales.append({
                            "address": holder.get("address"),
                            "symbol": symbol.upper(),
                            "rank": rank,
                            "balance": float(holder.get("balance", 0)),
                            "share": holder.get("share", 0),
                            "last_tx": None
                        })
                    return whales

                elif resp.status_code == 429:
                    print(f"⚠️ Ethplorer rate limit hit for {symbol}, retrying...")
                    await asyncio.sleep(3 * (attempt + 1))
                else:
                    print(f"❌ Ethplorer error {resp.status_code} for {symbol}: {resp.text[:120]}")
                    return []
            except Exception as e:
                print(f"⚠️ Ethplorer request error for {symbol}: {e}")
                await asyncio.sleep(2)
    return []


# ✅ Helper: Save fallback data
def save_fallback(symbol: str, reason: str):
    data = {
        "symbol": symbol.upper(),
        "unsupported": True,
        "reason": reason,
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    }
    save_path = os.path.join(WHALE_DATA_DIR, f"{symbol.upper()}.json")
    with open(save_path, "w") as wf:
        json.dump(data, wf, indent=2)
    print(f"⚠️ Skipped {symbol}: {reason}")


# ✅ Main whale refresh logic (with resume and version tracking)
async def refresh_all_whales(context=None):
    if not os.path.exists(TOP_TOKENS_FILE):
        print("❌ top100_coingecko_ids.json not found! Run refresh_top_tokens() first.")
        return False

    # ✅ FIX: Use the normalizer so it works regardless of JSON format
    tokens = load_tokens_as_list(TOP_TOKENS_FILE)

    total_tokens = len(tokens)
    print(f"🐋 Refreshing whales for {total_tokens} top tokens...")

    # ✅ Resume progress if available
    start_index = 0
    if LAST_PROGRESS["last_completed"]:
        last_symbol = LAST_PROGRESS["last_completed"]
        # ✅ FIX: Now tokens is always a list of dicts, so .get() works correctly
        for i, t in enumerate(tokens):
            if t.get("symbol", "").upper() == last_symbol:
                start_index = i + 1
                break
        print(f"🔄 Resuming from {last_symbol} (index {start_index})...")

    for t in tokens[start_index:]:
        # ✅ FIX: Now these always work because tokens is normalized
        token_id = t.get("id")
        symbol = t.get("symbol", "").upper()

        if not token_id or not symbol:
            print(f"⚠️ Skipping malformed token entry: {t}")
            continue

        # 🔍 Get cached or fresh contract
        contract_address = await get_contract_address(token_id, symbol)
        if not contract_address:
            save_fallback(symbol, "Non-ERC20 token or missing Ethereum contract")
            LAST_PROGRESS["last_completed"] = symbol
            save_cache_and_progress()
            continue

        print(f"🔹 Fetching whales for {symbol} ({contract_address})...")
        whales = await fetch_top_holders_ethplorer(contract_address, symbol)

        save_path = os.path.join(WHALE_DATA_DIR, f"{symbol}.json")
        if whales:
            # ✅ Add version tracking + timestamp
            whale_data = {
                "token": symbol,
                "contract": contract_address,
                "updated_at": datetime.utcnow().isoformat(),
                "version": "1.0.0",
                "whale_count": len(whales),
                "whales": whales
            }
            with open(save_path, "w") as wf:
                json.dump(whale_data, wf, indent=2)
            print(f"✅ Saved {len(whales)} whales for {symbol}")
        else:
            save_fallback(symbol, "No whale data available from Ethplorer")

        # ✅ Update progress after each token
        LAST_PROGRESS["last_completed"] = symbol
        save_cache_and_progress()

        await asyncio.sleep(1.5)

    print(f"✅ Whale data refresh completed at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    return True


# ✅ Entry point
if __name__ == "__main__":
    asyncio.run(refresh_all_whales())