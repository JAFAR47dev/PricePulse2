import asyncio
import httpx
import json
import os
import time
from datetime import datetime
from typing import List, Dict, Optional, Set
from pathlib import Path

# ============================================================================
# CONFIGURATION
# ============================================================================

ETHERSCAN_BASE = "https://api.etherscan.io/api"
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "YOUR_API_KEY_HERE")
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30.0
RETRY_DELAY = 2
STATE_CLEANUP_DAYS = 7

# File paths
STATE_FILE = "whales/last_seen.json"
USER_TRACK_FILE = "whales/user_tracking.json"
WHALE_DATA_DIR = "whales/data"

# Monitoring settings
WHALE_CHECK_INTERVAL = 300  # 5 minutes
MAX_CONCURRENT_REQUESTS = 10  # Limit concurrent API calls
ALERT_DELAY = 0.3  # Delay between sending alerts

# ============================================================================
# RATE LIMITER
# ============================================================================

class RateLimiter:
    """Simple rate limiter to avoid overwhelming APIs"""
    def __init__(self, delay=0.2):
        self.delay = delay
        self.last_call = 0
        self.lock = asyncio.Lock()
    
    async def wait(self):
        async with self.lock:
            now = asyncio.get_event_loop().time()
            time_since_last = now - self.last_call
            if time_since_last < self.delay:
                await asyncio.sleep(self.delay - time_since_last)
            self.last_call = asyncio.get_event_loop().time()

rate_limiter = RateLimiter()

# ============================================================================
# FILE I/O HELPERS
# ============================================================================

async def load_json_async(filepath: str, default=None):
    """Load JSON file asynchronously"""
    try:
        path = Path(filepath)
        if not path.exists():
            return default if default is not None else {}
        
        # Use asyncio to avoid blocking
        loop = asyncio.get_event_loop()
        content = await loop.run_in_executor(None, path.read_text)
        return json.loads(content)
    except Exception as e:
        print(f"⚠️ Error loading {filepath}: {e}")
        return default if default is not None else {}

async def save_json_async(filepath: str, data):
    """Save JSON file asynchronously"""
    try:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Use asyncio to avoid blocking
        loop = asyncio.get_event_loop()
        content = json.dumps(data, indent=2)
        await loop.run_in_executor(None, path.write_text, content)
        return True
    except Exception as e:
        print(f"⚠️ Error saving {filepath}: {e}")
        return False

def cleanup_old_state(state: Dict, max_age_days: int = STATE_CLEANUP_DAYS) -> Dict:
    """Remove state entries older than max_age_days"""
    if not isinstance(state, dict):
        return {}
    
    cutoff_time = time.time() - (max_age_days * 86400)
    cleaned = {}
    removed_count = 0
    
    for key, value in state.items():
        if isinstance(value, dict):
            timestamp = value.get("timestamp", 0)
            if timestamp > cutoff_time:
                cleaned[key] = value
            else:
                removed_count += 1
        else:
            # Keep old format entries for now (migration)
            cleaned[key] = value
    
    if removed_count > 0:
        print(f"🧹 Cleaned up {removed_count} old state entries")
    
    return cleaned

# ============================================================================
# ETHERSCAN API
# ============================================================================

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
                        wait_time = RETRY_DELAY * (attempt + 1)
                        print(f"⚠️ Etherscan rate limit hit, waiting {wait_time}s...")
                        await asyncio.sleep(wait_time)
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

# ============================================================================
# ALERT SENDING (Mock - Replace with your implementation)
# ============================================================================

async def send_whale_alert(user_id: str, message: str) -> bool:
    """Send alert to user via Telegram"""
    try:
        # Get bot token from environment
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not bot_token:
            print("⚠️ TELEGRAM_BOT_TOKEN not set in environment")
            return False
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        
        payload = {
            "chat_id": user_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            
            if response.status_code == 200:
                return True
            else:
                error_data = response.json()
                print(f"⚠️ Telegram API error for user {user_id}: {error_data}")
                return False
    
    except httpx.TimeoutException:
        print(f"⚠️ Timeout sending alert to {user_id}")
        return False
    except Exception as e:
        print(f"⚠️ Error sending alert to {user_id}: {e}")
        return False

# ============================================================================
# WHALE PROCESSING
# ============================================================================

async def process_whale(
    whale: Dict,
    symbol: str,
    contract: str,
    user_id: str,
    last_seen: Dict,
    rank: int
) -> Optional[Dict]:
    """
    Process a single whale and return alert data if there's new activity.
    Returns: Dict with alert info or None if no alert needed
    """
    if not isinstance(whale, dict):
        return None
    
    address = whale.get("address")
    if not address:
        return None
    
    try:
        # Fetch transactions
        txs = await fetch_whale_transactions(address, contract, symbol)
        
        if not txs:
            return None
        
        latest_tx = txs[0]
        tx_hash = latest_tx.get("hash")
        
        if not tx_hash:
            return None
        
        # Check if already seen
        last_key = f"{symbol}:{address}"
        
        # Get last known hash
        if isinstance(last_seen.get(last_key), dict):
            last_hash = last_seen[last_key].get("hash")
        else:
            last_hash = last_seen.get(last_key)
        
        if last_hash == tx_hash:
            return None  # No new movement
        
        # Format transaction details
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
        
        return {
            "user_id": user_id,
            "message": alert_msg,
            "state_key": last_key,
            "tx_hash": tx_hash,
            "symbol": symbol,
            "address": address
        }
    
    except (ValueError, TypeError, KeyError) as e:
        print(f"⚠️ Error processing whale {address[:8]} for {symbol}: {e}")
        return None

async def process_token_whales(
    symbol: str,
    contract: str,
    whales: List[Dict],
    user_id: str,
    last_seen: Dict,
    limit: int
) -> List[Dict]:
    """
    Process all whales for a token concurrently with controlled concurrency.
    Returns: List of alert data for new whale movements
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    
    async def process_with_semaphore(whale, rank):
        async with semaphore:
            return await process_whale(whale, symbol, contract, user_id, last_seen, rank)
    
    # Create tasks for all whales
    tasks = []
    for idx, whale in enumerate(whales[:limit]):
        rank = whale.get("rank", idx + 1)
        task = process_with_semaphore(whale, rank)
        tasks.append(task)
    
    # Process concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Filter out None and exceptions
    alerts = []
    for result in results:
        if isinstance(result, Exception):
            print(f"⚠️ Task failed with exception: {result}")
        elif result is not None:
            alerts.append(result)
    
    return alerts

# ============================================================================
# MAIN MONITORING LOOP
# ============================================================================

async def monitor_whales():
    """Main monitoring loop with improved error handling and concurrency"""
    start_time = time.time()
    print(f"\n{'='*60}")
    print(f"🐋 Whale Monitor Cycle Started")
    print(f"   Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"{'='*60}\n")
    
    # Load state
    last_seen = await load_json_async(STATE_FILE, {})
    user_tracking = await load_json_async(USER_TRACK_FILE, {})
    
    # Validate user tracking data
    if not user_tracking or not isinstance(user_tracking, dict):
        print("⚠️ No users are tracking whales yet.")
        print("   Waiting for next cycle...\n")
        return
    
    # Metrics
    stats = {
        "users_checked": 0,
        "tokens_checked": 0,
        "whales_monitored": 0,
        "alerts_sent": 0,
        "errors": 0
    }
    
    # Process each user's tracked tokens
    for user_id, data in user_tracking.items():
        if not isinstance(data, dict):
            continue
        
        stats["users_checked"] += 1
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
            
            # Validate and clamp limit
            limit = max(1, min(limit, 100))
            
            # Load whale data
            whale_file = Path(WHALE_DATA_DIR) / f"{symbol}.json"
            if not whale_file.exists():
                continue
            
            whale_data = await load_json_async(str(whale_file))
            
            if not isinstance(whale_data, dict):
                continue
            
            if whale_data.get("unsupported"):
                continue
            
            contract = whale_data.get("contract")
            whales = whale_data.get("whales", [])
            
            if not contract or not isinstance(whales, list):
                continue
            
            stats["tokens_checked"] += 1
            stats["whales_monitored"] += min(len(whales), limit)
            
            print(f"📊 Checking {symbol} ({len(whales[:limit])} whales) for user {user_id}")
            
            # Process whales concurrently
            alerts = await process_token_whales(
                symbol, contract, whales, user_id, last_seen, limit
            )
            
            # Send alerts and update state
            for alert in alerts:
                try:
                    success = await send_whale_alert(alert["user_id"], alert["message"])
                    
                    if success:
                        stats["alerts_sent"] += 1
                        
                        # Update state
                        last_seen[alert["state_key"]] = {
                            "hash": alert["tx_hash"],
                            "timestamp": time.time()
                        }
                        
                        print(f"   ✅ Sent alert for {alert['symbol']} whale {alert['address'][:8]}...")
                    else:
                        stats["errors"] += 1
                    
                    # Delay between alerts to avoid spam
                    await asyncio.sleep(ALERT_DELAY)
                
                except Exception as e:
                    print(f"   ⚠️ Error sending alert: {e}")
                    stats["errors"] += 1
    
    # Cleanup old state entries
    last_seen = cleanup_old_state(last_seen)
    
    # Save state
    await save_json_async(STATE_FILE, last_seen)
    
    # Calculate duration
    duration = time.time() - start_time
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"✅ Whale Monitor Cycle Completed")
    print(f"   Duration: {duration:.2f}s")
    print(f"   Users checked: {stats['users_checked']}")
    print(f"   Tokens checked: {stats['tokens_checked']}")
    print(f"   Whales monitored: {stats['whales_monitored']}")
    print(f"   Alerts sent: {stats['alerts_sent']}")
    print(f"   Errors: {stats['errors']}")
    print(f"{'='*60}\n")

# ============================================================================
# CONTINUOUS MONITORING
# ============================================================================

async def start_monitor(context):
    """Run the monitor continuously with error recovery"""
    print("🚀 Starting continuous whale monitoring...")
    print(f"   Check interval: {WHALE_CHECK_INTERVAL}s")
    print(f"   Max concurrent requests: {MAX_CONCURRENT_REQUESTS}")
    print(f"   State cleanup: {STATE_CLEANUP_DAYS} days\n")
    
    try:
        await monitor_whales()
    except Exception as e:
        print(f"❌ Critical error in monitor cycle: {e}")
        print(f"   Will retry on next scheduled run...\n")
        
# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    try:
        asyncio.run(start_monitor(context))
    except KeyboardInterrupt:
        print("\n\n🛑 Monitor stopped by user")
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")