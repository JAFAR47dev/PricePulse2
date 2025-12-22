import os
import json
import asyncio
import httpx
import aiofiles
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError, RetryAfter, TimedOut
from typing import Dict, List, Optional, Any
import time

# === Load environment variables ===
load_dotenv()
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not ETHERSCAN_API_KEY or not TELEGRAM_BOT_TOKEN:
    raise ValueError("Missing required environment variables: ETHERSCAN_API_KEY or TELEGRAM_BOT_TOKEN")

bot = Bot(token=TELEGRAM_BOT_TOKEN)

# === Directories ===
WHALE_DATA_DIR = "whales/data"
USER_TRACK_FILE = "whales/user_tracking.json"
STATE_FILE = "whales/last_seen.json"
os.makedirs(WHALE_DATA_DIR, exist_ok=True)

ETHERSCAN_BASE = "https://api.etherscan.io/api"

# === Configuration ===
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds
REQUEST_TIMEOUT = 15.0
RATE_LIMIT_DELAY = 0.2  # 200ms between API calls (5 req/sec)
STATE_CLEANUP_DAYS = 30  # Remove entries older than 30 days
MAX_STATE_ENTRIES = 10000  # Prevent unbounded growth


# === Rate limiter ===
class RateLimiter:
    """Simple rate limiter for API calls"""
    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self.last_call = 0
    
    async def wait(self):
        """Wait if necessary to respect rate limit"""
        now = time.time()
        time_since_last = now - self.last_call
        if time_since_last < self.min_interval:
            await asyncio.sleep(self.min_interval - time_since_last)
        self.last_call = time.time()


rate_limiter = RateLimiter(RATE_LIMIT_DELAY)


# === Helper: Load/save user tracking with async file I/O ===
async def load_json_async(path: str, default: Any = None) -> Dict:
    """Load JSON file asynchronously"""
    if not os.path.exists(path):
        return default or {}
    
    try:
        async with aiofiles.open(path, "r") as f:
            content = await f.read()
            if not content.strip():
                return default or {}
            return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"⚠️ Error parsing JSON from {path}: {e}")
        return default or {}
    except Exception as e:
        print(f"⚠️ Error loading {path}: {e}")
        return default or {}


async def save_json_async(path: str, data: Dict) -> bool:
    """Save JSON file asynchronously with atomic write"""
    try:
        # Write to temporary file first
        temp_path = f"{path}.tmp"
        async with aiofiles.open(temp_path, "w") as f:
            await f.write(json.dumps(data, indent=2))
        
        # Atomic rename
        os.replace(temp_path, path)
        return True
    except Exception as e:
        print(f"⚠️ Error saving {path}: {e}")
        return False


def load_json_sync(path: str, default: Any = None) -> Dict:
    """Synchronous JSON loader (for backwards compatibility)"""
    if not os.path.exists(path):
        return default or {}
    
    try:
        with open(path, "r") as f:
            content = f.read()
            if not content.strip():
                return default or {}
            return json.loads(content)
    except Exception as e:
        print(f"⚠️ Error loading {path}: {e}")
        return default or {}


def save_json_sync(path: str, data: Dict) -> bool:
    """Synchronous JSON saver (for backwards compatibility)"""
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"⚠️ Error saving {path}: {e}")
        return False


# === Cleanup old state entries ===
def cleanup_old_state(last_seen: Dict, max_age_days: int = STATE_CLEANUP_DAYS) -> Dict:
    """Remove old entries to prevent unbounded growth"""
    if len(last_seen) <= MAX_STATE_ENTRIES:
        return last_seen
    
    # Remove oldest entries if too many
    sorted_items = sorted(last_seen.items(), key=lambda x: x[1].get("timestamp", 0), reverse=True)
    cleaned = dict(sorted_items[:MAX_STATE_ENTRIES])
    
    removed = len(last_seen) - len(cleaned)
    if removed > 0:
        print(f"🧹 Cleaned up {removed} old state entries")
    
    return cleaned


# === Fetch latest transactions from Etherscan with retry ===
async def fetch_whale_transactions(
    address: str,
    contract: str,
    symbol: str,
    limit: int = 5
) -> List[Dict]:
    """
    Get recent ERC20 token transfers for an address with retry logic.
    Docs: https://docs.etherscan.io/api-endpoints/accounts#get-a-list-of-erc20-token-transfer-events-by-address
    """
    if not address or not contract:
        return []
    
    url = (
        f"{ETHERSCAN_BASE}?module=account&action=tokentx"
        f"&address={address}&contractaddress={contract}"
        f"&sort=desc&apikey={ETHERSCAN_API_KEY}"
    )
    
    for attempt in range(MAX_RETRIES):
        try:
            # Rate limiting
            await rate_limiter.wait()
            
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                resp = await client.get(url)
                
                if resp.status_code == 200:
                    data = resp.json()
                    
                    # Check for API errors
                    if data.get("status") == "0" and "rate limit" in data.get("message", "").lower():
                        print(f"⚠️ Etherscan rate limit hit, waiting...")
                        await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                        continue
                    
                    if data.get("status") == "1" and data.get("result"):
                        return data["result"][:limit]
                    
                    # Valid response but no results
                    return []
                
                elif resp.status_code == 429:  # Too Many Requests
                    wait_time = RETRY_DELAY * (attempt + 1)
                    print(f"⚠️ Rate limited, waiting {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                
                else:
                    print(f"⚠️ Etherscan returned status {resp.status_code}")
                    return []
        
        except httpx.TimeoutException:
            print(f"⚠️ Timeout fetching tx for {symbol} whale {address[:6]}... (attempt {attempt + 1}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)
        
        except Exception as e:
            print(f"⚠️ Error fetching tx for {symbol} whale {address[:6]}...: {e}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)
    
    return []


# === Detect large movements ===
def is_large_transaction(tx: Dict) -> bool:
    """
    Simple heuristic — treat as 'large' if > 500k tokens.
    You can refine this logic later using live price data.
    """
    try:
        value = float(tx.get("value", 0)) / (10 ** int(tx.get("tokenDecimal", 18)))
        return value > 500_000  # placeholder threshold
    except (ValueError, TypeError, ZeroDivisionError):
        return False


# === Send alert with retry ===
async def send_whale_alert(user_id: str, alert_msg: str) -> bool:
    """Send Telegram alert with retry logic"""
    for attempt in range(MAX_RETRIES):
        try:
            await bot.send_message(
                chat_id=user_id,
                text=alert_msg,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
            return True
        
        except RetryAfter as e:
            # Telegram rate limit
            wait_time = e.retry_after + 1
            print(f"⚠️ Telegram rate limit, waiting {wait_time}s...")
            await asyncio.sleep(wait_time)
        
        except TimedOut:
            print(f"⚠️ Telegram timeout (attempt {attempt + 1}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)
        
        except TelegramError as e:
            print(f"⚠️ Telegram error sending to {user_id}: {e}")
            if "bot was blocked" in str(e).lower() or "user is deactivated" in str(e).lower():
                # User blocked bot or deactivated - don't retry
                return False
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)
        
        except Exception as e:
            print(f"⚠️ Unexpected error sending to {user_id}: {e}")
            return False
    
    return False


# === Monitor task ===
async def monitor_whales():
    """Main monitoring loop"""
    print(f"🐋 Starting whale monitor at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    
    # Load state
    last_seen = await load_json_async(STATE_FILE, {})
    user_tracking = await load_json_async(USER_TRACK_FILE, {})
    
    if not user_tracking:
        print("⚠️ No users are tracking whales yet.")
        return
    
    if not isinstance(user_tracking, dict):
        print("⚠️ Invalid user tracking data format")
        return
    
    alerts_sent = 0
    errors_count = 0
    
    for user_id, data in user_tracking.items():
        if not isinstance(data, dict):
            continue
        
        tracked = data.get("tracked", [])
        if not isinstance(tracked, list):
            continue
        
        for item in tracked:
            if not isinstance(item, dict):
                continue
            
            symbol = item.get("token")
            limit = item.get("limit", 5)
            
            if not symbol or not isinstance(limit, int):
                continue
            
            # Validate limit
            limit = max(1, min(limit, 50))
            
            whale_file = os.path.join(WHALE_DATA_DIR, f"{symbol}.json")
            if not os.path.exists(whale_file):
                continue
            
            # Load whale data
            whale_data = load_json_sync(whale_file)
            
            if not isinstance(whale_data, dict):
                continue
            
            if whale_data.get("unsupported"):
                continue
            
            contract = whale_data.get("contract")
            whales = whale_data.get("whales", [])
            
            if not contract or not isinstance(whales, list):
                continue
            
            whales = whales[:limit]
            
            for whale in whales:
                if not isinstance(whale, dict):
                    continue
                
                address = whale.get("address")
                rank = whale.get("rank")
                
                if not address:
                    continue
                
                # Fetch transactions
                txs = await fetch_whale_transactions(address, contract, symbol)
                
                if not txs:
                    continue
                
                latest_tx = txs[0]
                tx_hash = latest_tx.get("hash")
                
                if not tx_hash:
                    continue
                
                # Check if already seen
                last_key = f"{symbol}:{address}"
                
                # Store with timestamp for cleanup
                if isinstance(last_seen.get(last_key), dict):
                    last_hash = last_seen[last_key].get("hash")
                else:
                    last_hash = last_seen.get(last_key)
                
                if last_hash == tx_hash:
                    continue  # No new movement
                
                # Update state with timestamp
                last_seen[last_key] = {
                    "hash": tx_hash,
                    "timestamp": time.time()
                }
                
                # Format transaction details
                try:
                    value = float(latest_tx.get("value", 0)) / (10 ** int(latest_tx.get("tokenDecimal", 18)))
                    from_addr = latest_tx.get("from", "").lower()
                    to_addr = latest_tx.get("to", "").lower()
                    
                    direction = "OUTFLOW" if from_addr == address.lower() else "INFLOW"
                    formatted_value = f"{value:,.0f}"
                    
                    alert_msg = (
                        f"🐳 *Whale Alert!*\n\n"
                        f"Token: *{symbol}*\n"
                        f"Whale Rank: #{rank}\n"
                        f"Movement: *{direction}*\n"
                        f"Amount: `{formatted_value} {symbol}`\n"
                        f"Tx: [{tx_hash[:10]}...](https://etherscan.io/tx/{tx_hash})\n"
                        f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
                    )
                    
                    # Send alert
                    success = await send_whale_alert(user_id, alert_msg)
                    
                    if success:
                        alerts_sent += 1
                        print(f"📩 Sent whale alert to user {user_id} for {symbol}")
                    else:
                        errors_count += 1
                    
                    # Small delay between alerts
                    await asyncio.sleep(0.3)
                
                except (ValueError, TypeError, KeyError) as e:
                    print(f"⚠️ Error formatting alert for {symbol}: {e}")
                    errors_count += 1
                    continue
    
    # Cleanup old state entries
    last_seen = cleanup_old_state(last_seen)
    
    # Save state
    await save_json_async(STATE_FILE, last_seen)
    
    print(f"✅ Whale monitor completed: {alerts_sent} alerts sent, {errors_count} errors")


async def start_monitor(context):
    """Runs once every scheduled interval (handled by JobQueue)"""
    try:
        await monitor_whales()
    except Exception as e:
        print(f"[WhaleMonitor] Critical error in start_monitor: {e}")
        import traceback
        traceback.print_exc()


# === Manual test entry point ===
if __name__ == "__main__":
    asyncio.run(monitor_whales())