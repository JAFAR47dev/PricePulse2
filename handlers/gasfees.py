import os
import requests
from typing import Optional, Dict
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

load_dotenv()
BLOCKNATIVE_API_KEY = os.getenv("BLOCKNATIVE_API_KEY")

BLOCKNATIVE_API_URL = "https://api.blocknative.com/gasprices/blockprices"
REQUEST_TIMEOUT = 10
MIN_CONFIDENCE_THRESHOLD = 70

GAS_UNITS = {
    "transfer": 21000,
    "erc20": 65000,
    "swap": 150000,
    "nft_mint": 100000,
}


class GasFeeError(Exception):
    pass


def validate_api_key() -> bool:
    return bool(BLOCKNATIVE_API_KEY and BLOCKNATIVE_API_KEY.strip())


def get_eth_price() -> Optional[float]:
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
    eth_cost = (gwei_price * gas_units) / 1e9
    return eth_cost * eth_price


def extract_gas_prices(block_data: Dict) -> Dict[str, float]:
    estimated_prices = block_data.get("estimatedPrices", [])
    
    if not estimated_prices:
        raise GasFeeError("No gas price estimates available")
    
    reliable_prices = [
        p for p in estimated_prices 
        if p.get("confidence", 0) >= MIN_CONFIDENCE_THRESHOLD
    ]
    
    if not reliable_prices:
        reliable_prices = estimated_prices
    
    reliable_prices.sort(key=lambda x: x.get("price", float('inf')))
    
    num_prices = len(reliable_prices)
    
    if num_prices == 0:
        raise GasFeeError("No valid price data")
    elif num_prices == 1:
        price = reliable_prices[0]["price"]
        return {"low": price, "standard": price, "high": price}
    elif num_prices == 2:
        return {
            "low": reliable_prices[0]["price"],
            "standard": (reliable_prices[0]["price"] + reliable_prices[1]["price"]) / 2,
            "high": reliable_prices[1]["price"]
        }
    else:
        return {
            "low": reliable_prices[0]["price"],
            "standard": reliable_prices[num_prices // 2]["price"],
            "high": reliable_prices[-1]["price"]
        }


# ============================================================================
# DATA FUNCTION (for notifications)
# ============================================================================

def get_gas_fees_data() -> dict:
    """
    Fetch gas fees and return raw data as dict.
    
    Returns:
        dict: {'low': str, 'standard': str, 'high': str} or empty dict on error
    """
    if not validate_api_key():
        return {}
    
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
        blocks = data.get("blockPrices")
        
        if not blocks or len(blocks) == 0:
            return {}
        
        block = blocks[0]
        prices = extract_gas_prices(block)
        
        return {
            "low": f"{prices['low']:.1f} Gwei",
            "standard": f"{prices['standard']:.1f} Gwei",
            "high": f"{prices['high']:.1f} Gwei"
        }
        
    except Exception as e:
        print(f"[Gas Fees Data] Error: {e}")
        return {}


# ============================================================================
# MESSAGE FUNCTION (for Telegram commands)
# ============================================================================

def format_usd_costs(prices: Dict[str, float], eth_price: float, tx_type: str = "transfer") -> str:
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
    """Fetch Ethereum gas fees and return a formatted string."""
    if not validate_api_key():
        return "⚠️ *Configuration Error*\n\nBlocknative API key is not configured."
    
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
        blocks = data.get("blockPrices")
        
        if not blocks or len(blocks) == 0:
            raise GasFeeError("Invalid API response structure")
        
        block = blocks[0]
        block_number = block.get("blockNumber", "Unknown")
        base_fee = block.get("baseFeePerGas")
        
        prices = extract_gas_prices(block)
        eth_price = get_eth_price()
        
        text = f"⛽ *Ethereum Gas Fees*\n\n"
        
        if eth_price:
            text += f"💸 *ETH Transfer (~{GAS_UNITS['transfer']:,} gas)*\n"
            text += format_usd_costs(prices, eth_price, "transfer")
            
            text += f"\n🪙 *ERC-20 Transfer (~{GAS_UNITS['erc20']:,} gas)*\n"
            text += format_usd_costs(prices, eth_price, "erc20")
            
            text += f"\n🔄 *DEX Swap (~{GAS_UNITS['swap']:,} gas)*\n"
            text += format_usd_costs(prices, eth_price, "swap")
            
            text += f"\n💎 *ETH Price:* ${eth_price:,.2f}\n"
        else:
            text += (
                f"• Low: `{prices['low']:.1f}` Gwei\n"
                f"• Standard: `{prices['standard']:.1f}` Gwei\n"
                f"• High: `{prices['high']:.1f}` Gwei\n\n"
            )
            text += "⚠️ _USD estimates unavailable_\n"
        
        if base_fee:
            text += f"📊 Base Fee: `{base_fee:.1f}` Gwei\n"
        
        text += (
            f"🧱 Block: `{block_number}`\n\n"
            f"_Gas costs are approximate_"
        )
        
        return text
        
    except Exception as e:
        print(f"[Gas Fees] Error: {e}")
        return "⚠️ Failed to fetch gas fees."


# ============================================================================
# TELEGRAM COMMAND HANDLER
# ============================================================================

async def gasfees_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        await update_last_active(user_id, command_name="/gas")
        await handle_streak(update, context)
        
        text = get_gas_fees()
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        
    except Exception as e:
        print(f"[Gas Command] Error: {e}")
        await update.message.reply_text("⚠️ An error occurred.")