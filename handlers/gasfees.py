import os
import requests
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

load_dotenv()
BLOCKNATIVE_API_KEY = os.getenv("BLOCKNATIVE_API_KEY")

# Constants
BLOCKNATIVE_API_URL = "https://api.blocknative.com/gasprices/blockprices"
REQUEST_TIMEOUT = 10
MIN_CONFIDENCE_THRESHOLD = 70  # Only use estimates with 70%+ confidence

# Gas units for common transactions
GAS_UNITS = {
    "transfer": 21000,          # Simple ETH transfer
    "erc20": 65000,             # ERC-20 token transfer
    "swap": 150000,             # Uniswap/DEX swap
    "nft_mint": 100000,         # NFT minting
}

class GasFeeError(Exception):
    """Custom exception for gas fee fetching errors"""
    pass


def validate_api_key() -> bool:
    """Validate that API key is configured"""
    return bool(BLOCKNATIVE_API_KEY and BLOCKNATIVE_API_KEY.strip())


def get_eth_price() -> Optional[float]:
    """
    Fetch current ETH price in USD from CoinGecko.
    Returns None if fetch fails.
    """
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": "ethereum", "vs_currencies": "usd"}
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        return data.get("ethereum", {}).get("usd")
    except Exception as e:
        print(f"[ETH Price] Failed to fetch: {e}")
        return None


def calculate_gas_cost_usd(gwei_price: float, gas_units: int, eth_price: float) -> float:
    """
    Calculate gas cost in USD.
    
    Args:
        gwei_price: Gas price in Gwei
        gas_units: Number of gas units for the transaction
        eth_price: Current ETH price in USD
    
    Returns:
        Cost in USD
    """
    # Convert Gwei to ETH (1 ETH = 1e9 Gwei)
    eth_cost = (gwei_price * gas_units) / 1e9
    return eth_cost * eth_price


def extract_gas_prices(block_data: Dict[str, Any]) -> Dict[str, float]:
    """
    Extract and categorize gas prices from block data.
    
    Returns dict with 'low', 'standard', 'high' keys.
    """
    estimated_prices = block_data.get("estimatedPrices", [])
    
    if not estimated_prices:
        raise GasFeeError("No gas price estimates available")
    
    # Filter by confidence threshold and sort by price (ascending)
    reliable_prices = [
        p for p in estimated_prices 
        if p.get("confidence", 0) >= MIN_CONFIDENCE_THRESHOLD
    ]
    
    # Fallback to all prices if none meet threshold
    if not reliable_prices:
        reliable_prices = estimated_prices
    
    # Sort by price ascending
    reliable_prices.sort(key=lambda x: x.get("price", float('inf')))
    
    num_prices = len(reliable_prices)
    
    if num_prices == 0:
        raise GasFeeError("No valid price data")
    elif num_prices == 1:
        # Only one price available
        price = reliable_prices[0]["price"]
        return {"low": price, "standard": price, "high": price}
    elif num_prices == 2:
        # Two prices: use as low and high
        return {
            "low": reliable_prices[0]["price"],
            "standard": (reliable_prices[0]["price"] + reliable_prices[1]["price"]) / 2,
            "high": reliable_prices[1]["price"]
        }
    else:
        # Three or more: use low, median, high
        return {
            "low": reliable_prices[0]["price"],
            "standard": reliable_prices[num_prices // 2]["price"],
            "high": reliable_prices[-1]["price"]
        }


def format_usd_costs(prices: Dict[str, float], eth_price: float, tx_type: str = "transfer") -> str:
    """
    Format USD cost estimates for a transaction type.
    
    Args:
        prices: Dict with 'low', 'standard', 'high' gas prices in Gwei
        eth_price: Current ETH price in USD
        tx_type: Type of transaction (default: "transfer")
    
    Returns:
        Formatted string with USD estimates
    """
    gas_units = GAS_UNITS.get(tx_type, GAS_UNITS["transfer"])
    
    low_usd = calculate_gas_cost_usd(prices["low"], gas_units, eth_price)
    standard_usd = calculate_gas_cost_usd(prices["standard"], gas_units, eth_price)
    high_usd = calculate_gas_cost_usd(prices["high"], gas_units, eth_price)
    
    return (
        f"• Low: `{prices['low']:.1f}` Gwei (~${low_usd:.2f})\n"
        f"• Standard: `{prices['standard']:.1f}` Gwei (~${standard_usd:.2f})\n"
        f"• High: `{prices['high']:.1f}` Gwei (~${high_usd:.2f})\n"
    )


def get_gas_fees() -> str:
    """
    Fetch Ethereum gas fees and return a formatted string.
    
    Returns:
        Formatted string with gas fee information or error message
    """
    if not validate_api_key():
        return "⚠️ *Configuration Error*\n\nBlocknative API key is not configured. Please check your .env file."
    
    try:
        headers = {
            "Authorization": BLOCKNATIVE_API_KEY,
            "Accept": "application/json"
        }
        
        response = requests.get(
            BLOCKNATIVE_API_URL, 
            headers=headers, 
            timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        
        data = response.json()
        
        # Validate response structure
        blocks = data.get("blockPrices")
        if not blocks or not isinstance(blocks, list) or len(blocks) == 0:
            raise GasFeeError("Invalid API response structure")
        
        block = blocks[0]
        block_number = block.get("blockNumber", "Unknown")
        base_fee = block.get("baseFeePerGas")
        
        # Extract categorized prices
        prices = extract_gas_prices(block)
        
        # Fetch ETH price
        eth_price = get_eth_price()
        
        # Build response text
        text = f"⛽ *Ethereum Gas Fees*\n\n"
        
        if eth_price:
            # Show costs for ETH transfer (most common)
            text += f"💸 *ETH Transfer (~{GAS_UNITS['transfer']:,} gas)*\n"
            text += format_usd_costs(prices, eth_price, "transfer")
            
            text += f"\n🪙 *ERC-20 Transfer (~{GAS_UNITS['erc20']:,} gas)*\n"
            text += format_usd_costs(prices, eth_price, "erc20")
            
            text += f"\n🔄 *DEX Swap (~{GAS_UNITS['swap']:,} gas)*\n"
            text += format_usd_costs(prices, eth_price, "swap")
            
            text += f"\n💎 *ETH Price:* ${eth_price:,.2f}\n"
        else:
            # Fallback if ETH price unavailable
            text += (
                f"• Low: `{prices['low']:.1f}` Gwei (slower)\n"
                f"• Standard: `{prices['standard']:.1f}` Gwei (balanced)\n"
                f"• High: `{prices['high']:.1f}` Gwei (fast)\n\n"
            )
            text += "⚠️ _USD estimates unavailable_\n"
        
        if base_fee:
            text += f"📊 Base Fee: `{base_fee:.1f}` Gwei\n"
        
        text += (
            f"🧱 Block: `{block_number}`\n\n"
            f"_Gas costs are approximate and vary by transaction complexity_"
        )
        
        return text
        
    except requests.exceptions.Timeout:
        print("[Gas Fees] Request timeout")
        return "⚠️ Request timed out. The gas fee service is taking too long to respond. Please try again."
        
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response else "Unknown"
        print(f"[Gas Fees] HTTP Error {status_code}: {e}")
        
        if status_code == 401:
            return "⚠️ *Authentication Error*\n\nInvalid API key. Please check your Blocknative API key configuration."
        elif status_code == 429:
            return "⚠️ *Rate Limit Exceeded*\n\nToo many requests. Please wait a moment and try again."
        else:
            return f"⚠️ Service error (HTTP {status_code}). Please try again later."
        
    except requests.exceptions.RequestException as e:
        print(f"[Gas Fees] Network error: {e}")
        return "⚠️ Network error. Please check your connection and try again."
        
    except GasFeeError as e:
        print(f"[Gas Fees] Data error: {e}")
        return f"⚠️ Data error: {e}"
        
    except (KeyError, ValueError, TypeError) as e:
        print(f"[Gas Fees] Parsing error: {e}")
        return "⚠️ Failed to parse gas fee data. The API response format may have changed."
        
    except Exception as e:
        print(f"[Gas Fees] Unexpected error: {type(e).__name__}: {e}")
        return "⚠️ An unexpected error occurred. Please try again later."


# --- Telegram command handler ---
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

async def gasfees_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /gas command"""
    try:
        user_id = update.effective_user.id
        
        # Update user activity
        await update_last_active(user_id, command_name="/gas")
        await handle_streak(update, context)
        
        # Fetch and send gas fees
        text = get_gas_fees()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        print(f"[Gas Command] Error: {e}")
        try:
            await update.message.reply_text(
                "⚠️ An error occurred while processing your request. Please try again."
            )
        except Exception as reply_error:
            print(f"[Gas Command] Failed to send error message: {reply_error}")
