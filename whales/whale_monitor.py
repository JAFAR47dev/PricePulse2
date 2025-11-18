import os
import json
import asyncio
import httpx
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Bot

# === Load environment variables ===
load_dotenv()
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

bot = Bot(token=TELEGRAM_BOT_TOKEN)

# === Directories ===
WHALE_DATA_DIR = "whales/data"
USER_TRACK_FILE = "whales/user_tracking.json"
STATE_FILE = "whales/last_seen.json"
os.makedirs(WHALE_DATA_DIR, exist_ok=True)

ETHERSCAN_BASE = "https://api.etherscan.io/api"


# === Helper: Load/save user tracking ===
def load_json(path, default=None):
    if not os.path.exists(path):
        return default or {}
    with open(path, "r") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# === Fetch latest transactions from Etherscan ===
async def fetch_whale_transactions(address: str, contract: str, symbol: str, limit=5):
    """
    Get recent ERC20 token transfers for an address.
    Docs: https://docs.etherscan.io/api-endpoints/accounts#get-a-list-of-erc20-token-transfer-events-by-address
    """
    url = (
        f"{ETHERSCAN_BASE}?module=account&action=tokentx"
        f"&address={address}&contractaddress={contract}"
        f"&sort=desc&apikey={ETHERSCAN_API_KEY}"
    )

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "1" and data.get("result"):
                    return data["result"][:limit]
        except Exception as e:
            print(f"⚠️ Error fetching tx for {symbol} whale {address[:6]}...: {e}")
    return []


# === Detect large movements ===
def is_large_transaction(tx):
    """
    Simple heuristic — treat as 'large' if > $100k or > 0.5% of supply.
    You can refine this logic later using live price data.
    """
    value = float(tx.get("value", 0)) / (10 ** int(tx.get("tokenDecimal", 18)))
    return value > 100_000  # placeholder threshold


# === Monitor task ===
async def monitor_whales():
    print("🐋 Starting whale monitor...")
    last_seen = load_json(STATE_FILE, {})

    user_tracking = load_json(USER_TRACK_FILE, {})
    if not user_tracking:
        print("⚠️ No users are tracking whales yet.")
        return

    for user_id, data in user_tracking.items():
        tracked = data.get("tracked", [])
        for item in tracked:
            symbol = item["token"]
            limit = item["limit"]

            whale_file = os.path.join(WHALE_DATA_DIR, f"{symbol}.json")
            if not os.path.exists(whale_file):
                continue

            with open(whale_file, "r") as wf:
                whale_data = json.load(wf)

            if whale_data.get("unsupported"):
                continue

            contract = whale_data.get("contract")
            whales = whale_data.get("whales", [])[:limit]

            for whale in whales:
                address = whale["address"]
                txs = await fetch_whale_transactions(address, contract, symbol)

                if not txs:
                    continue

                latest_tx = txs[0]
                tx_hash = latest_tx["hash"]

                # Check if already seen
                last_key = f"{symbol}:{address}"
                if last_seen.get(last_key) == tx_hash:
                    continue  # no new movement

                last_seen[last_key] = tx_hash  # update state
                value = float(latest_tx["value"]) / (10 ** int(latest_tx["tokenDecimal"]))
                direction = "outflow" if latest_tx["from"].lower() == address.lower() else "inflow"
                formatted_value = f"{value:,.0f}"

                alert_msg = (
                    f"🐳 *Whale Alert!*\n\n"
                    f"Token: *{symbol}*\n"
                    f"Whale Rank: #{whale['rank']}\n"
                    f"Movement: *{direction.upper()}*\n"
                    f"Amount: `{formatted_value} {symbol}`\n"
                    f"Tx Hash: [{tx_hash[:10]}...](https://etherscan.io/tx/{tx_hash})\n"
                    f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
                )

                try:
                    await bot.send_message(chat_id=user_id, text=alert_msg, parse_mode="Markdown", disable_web_page_preview=True)
                    print(f"📩 Sent whale alert to user {user_id} for {symbol}")
                except Exception as e:
                    print(f"⚠️ Failed to send alert to {user_id}: {e}")

                await asyncio.sleep(0.5)

    save_json(STATE_FILE, last_seen)
    print("✅ Whale monitor completed cycle.")


# === Run monitor periodically ===
async def start_monitor(interval_minutes=5):
    """Run whale monitor every N minutes"""
    while True:
        await monitor_whales()
        await asyncio.sleep(interval_minutes * 60)


# === Manual test entry point ===
if __name__ == "__main__":
    asyncio.run(monitor_whales())