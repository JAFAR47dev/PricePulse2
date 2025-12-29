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

class GasFeeError(Exception):
    """Custom exception for gas fee fetching errors"""
    pass


def validate_api_key() -> bool:
    """Validate that API key is configured"""
    return bool(BLOCKNATIVE_API_KEY and BLOCKNATIVE_API_KEY.strip())


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
        
        # Build response text
        text = (
            f"⛽ *Ethereum Gas Fees*\n\n"
            f"• Low: `{prices['low']:.1f}` Gwei (slower)\n"
            f"• Standard: `{prices['standard']:.1f}` Gwei (balanced)\n"
            f"• High: `{prices['high']:.1f}` Gwei (fast)\n\n"
        )
        
        if base_fee:
            text += f"📊 Base Fee: `{base_fee:.1f}` Gwei\n"
        
        text += (
            f"🧱 Block: `{block_number}`\n"
            f"🔍 _Powered by Blocknative_"
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