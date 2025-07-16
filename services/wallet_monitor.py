import asyncio
import httpx
from telegram import Bot
from models.wallet_tracker import get_all_tracked_wallets
from config import ETHERSCAN_API_KEY
from handlers.trackwallet import TOP_WHALES

ETHERSCAN_BASE = "https://api.etherscan.io/api"

async def fetch_wallet_tx(wallet):
    params = {
        "module": "account",
        "action": "tokentx",
        "address": wallet,
        "startblock": 0,
        "endblock": 99999999,
        "sort": "desc",
        "apikey": ETHERSCAN_API_KEY
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(ETHERSCAN_BASE, params=params, timeout=15)
            data = await response.json()
            return data.get("result", [])
    except Exception as e:
        print(f"❌ Error fetching Etherscan data for {wallet}: {e}")
        return []
        
async def monitor_wallets(bot: Bot):
    while True:
        print("🔍 Checking tracked wallets via Etherscan...")

        tracked = get_all_tracked_wallets()

        for entry in tracked:
            user_id = entry["user_id"]
            wallet = entry["wallet"]

            txs = await fetch_wallet_tx(wallet)
            if not txs:
                continue

            for tx in txs[:5]:  # Only check latest 5 txs
                try:
                    token_decimal = int(tx.get("tokenDecimal", 18))
                    value_raw = tx.get("value", "0")
                    value = int(value_raw) / (10 ** token_decimal)

                    symbol = tx.get("tokenSymbol", "UNKNOWN")
                    to_address = tx.get("to", "unknown")[:10] + "..."
                    tx_hash = tx.get("hash", "")

                    if value >= 1_000_000:  # 💰 Big transaction threshold
                        # Check if it's a known wallet
                        label = next((name for name, addr in TOP_WHALES.items() if addr.lower() == wallet.lower()), None)
                        display = label or f"Wallet `{wallet[:8]}...`"

                        msg = (
                            f"🐋 *Whale Alert!*\n"
                            f"*{display}* just transferred `{value:,.0f} {symbol}`\n"
                            f"→ To: `{to_address}`\n"
                            f"[🔗 View Tx](https://etherscan.io/tx/{tx_hash})"
                        )

                        await bot.send_message(
                            chat_id=user_id,
                            text=msg,
                            parse_mode="Markdown",
                            disable_web_page_preview=True
                        )

                except Exception as e:
                    print(f"⚠️ Skipping invalid tx: {e}")

        await asyncio.sleep(300)  # Wait 5 minutes