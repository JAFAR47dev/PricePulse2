# handlers/set_alert/set_alert.py
import json
import os
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from models.user import get_user_plan
from utils.auth import is_pro_plan
from tasks.handlers import handle_streak
from models.user_activity import update_last_active

# Import the new interactive flow starter
from handlers.set_alert.flow_manager import start_set_alert

# Import existing alert handlers (for backward compatibility)
from handlers.alert_handlers import (
    handle_price_alert,
    handle_percent_alert,
    handle_volume_alert,
    handle_risk_alert,
    handle_indicator_alert,
)

# ============================================================================
# COINGECKO TOP 200 VALIDATION
# ============================================================================

def load_supported_coins():
    """
    Load top 200 CoinGecko coins from JSON.
    Returns:
        dict: {SYMBOL: coingecko_id}
    """
    try:
        json_path = "services/top200_coingecko_ids.json"
        with open(json_path, "r") as f:
            data = json.load(f)
            
            if not isinstance(data, dict):
                raise ValueError("top200_coingecko_ids.json must be a dict")
            
            # Normalize symbols to uppercase
            coins = {symbol.upper(): cg_id for symbol, cg_id in data.items()}
            
            return coins
    
    except Exception as e:
        print(f"Error loading top 200 CoinGecko coins: {e}")
        # Return minimal fallback with major coins
        return {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "BNB": "binancecoin",
            "SOL": "solana",
            "XRP": "ripple"
        }

# Load supported coins at module level (cached)
SUPPORTED_COINS = load_supported_coins()

def is_valid_coin(symbol: str) -> bool:
    """Check if coin symbol is in top 200 CoinGecko list"""
    return symbol.upper() in SUPPORTED_COINS

def normalize_coin_symbol(symbol: str) -> str:
    """
    Normalize coin symbol (remove common suffixes like USDT, USD)
    Returns uppercase base symbol
    """
    s = symbol.upper().strip()
    # Remove common trading pair suffixes
    for suffix in ["USDT", "USD", "BUSD", "USDC", "BTC", "ETH"]:
        if s.endswith(suffix) and len(s) > len(suffix):
            s = s[:-len(suffix)]
            break
    return s

# ============================================================================
# MAIN COMMAND HANDLER
# ============================================================================

async def set_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Entry point for /set command.
    
    Usage modes:
    1. Interactive flow: /set (no args)
    2. Quick price alert: /set btc > 50000
    3. Legacy format: /set <alert_type> <args...> (hidden, for backward compatibility)
    """
    user_id = update.effective_user.id
    await update_last_active(user_id, command_name="/set")
    await handle_streak(update, context)
    plan = get_user_plan(user_id)
    
    # ✅ If user typed just /set → start interactive flow
    if not context.args:
        await start_set_alert(update, context)
        return
    
    # --- Parse arguments ---
    args = context.args
    first_arg = args[0].lower()
    
    # Define valid alert types for legacy format (backward compatibility only)
    valid_alert_types = ["price", "percent", "volume", "risk", "indicator"]
    
    # ✅ DECISION LOGIC:
    # If first arg is a known alert type → legacy format
    # Otherwise → try to parse as quick format (price alert)
    
    if first_arg in valid_alert_types:
        # === LEGACY FORMAT: /set <alert_type> <args...> (backward compatibility) ===
        alert_type = first_arg
        alert_args = args[1:]  # Remaining args after alert type
        
        # ✅ VALIDATE COIN SYMBOL (if provided)
        if alert_args:
            coin_symbol = normalize_coin_symbol(alert_args[0])
            
            if not is_valid_coin(coin_symbol):
                await update.message.reply_text(
                    f"❌ <b>{coin_symbol} is not supported</b>\n\n"
                    f"Alerts only work for top 200 CoinGecko coins.\n\n"
                    f"<b>Popular supported coins:</b>\n"
                    f"BTC, ETH, BNB, SOL, XRP, ADA, DOGE, MATIC, DOT, AVAX, LINK, UNI, etc.\n\n",
                    parse_mode=ParseMode.HTML
                )
                return
        
        handlers = {
            "price": handle_price_alert,
            "percent": handle_percent_alert,
            "volume": handle_volume_alert,
            "risk": handle_risk_alert,
            "indicator": handle_indicator_alert,
        }
        
        # 🚫 Enforce free plan limits
        if not is_pro_plan(plan) and alert_type != "price":
            await update.message.reply_text(
                "🔒 <b>Advanced alerts are for Pro users only.</b>\n\n"
                "💎 Use /upgrade to unlock percent, volume, risk, and indicator alerts.",
                parse_mode=ParseMode.HTML,
            )
            return
        
        # ✅ Pass to appropriate handler
        await handlers[alert_type](update, context, alert_args, plan)
    
    else:
        # === QUICK FORMAT: /set btc > 50000 ===
        # Assume it's a price alert and parse the entire args list
        
        # ✅ VALIDATE COIN SYMBOL FIRST
        coin_symbol = normalize_coin_symbol(first_arg)
        
        if not is_valid_coin(coin_symbol):
            await update.message.reply_text(
                f"❌ <b>{coin_symbol.upper()} is not supported</b>\n\n"
                f"Alerts only work for top 200 CoinGecko coins.\n\n"
                f"<b>Popular supported coins:</b>\n"
                f"BTC, ETH, BNB, SOL, XRP, ADA, DOGE, MATIC, DOT, AVAX, LINK, UNI, etc.\n\n"
                f"<b>Examples of valid alerts:</b>\n"
                f"• <code>/set BTC &gt; 50000</code>\n"
                f"• <code>/set ETH below 3000</code>\n"
                f"• <code>/set SOL above 100</code>",
                parse_mode=ParseMode.HTML
            )
            return
        
        # Check if it looks like a price alert expression
        if len(args) >= 3:  # Need at least: coin operator value
            # Only support > < above below
            supported_operators = [">", "<", "above", "below", "over", "under"]
            has_operator = any(op.lower() in supported_operators for op in args)
            
            if has_operator:
                # Looks like a price alert expression
                # Pass all args to price alert handler
                await handle_price_alert(update, context, args, plan)
            else:
                # Doesn't look valid - show help
                await _show_help_message(update, plan)
        else:
            # Too few arguments - show help
            await _show_help_message(update, plan)


async def _show_help_message(update: Update, plan: str):
    """Show simplified help message for /set command"""
    
    help_text = (
        "🔔 <b>How to Set Alerts</b>\n\n"
        
        "<b>Two easy ways:</b>\n\n"
        
        "1️⃣ <b>Interactive Setup</b> (Recommended)\n"
        "Just type: <code>/set</code>\n"
        "Then follow the step-by-step prompts to create any type of alert.\n\n"
        
        "2️⃣ <b>Quick Price Alert</b>\n"
        "For price alerts, you can use this shortcut:\n\n"
        "<b>Format:</b> <code>/set &lt;coin&gt; &lt;operator&gt; &lt;price&gt;</code>\n\n"
        
        "<b>Supported operators:</b>\n"
        "• <code>above</code>, <code>over</code> or <code>&gt;</code> — Alert when price goes above\n"
        "• <code>below</code>, <code>under</code> or <code>&lt;</code> — Alert when price goes below\n\n"
        
        "<b>Examples:</b>\n"
        "• <code>/set btc &gt; 50000</code>\n"
        "• <code>/set eth below 3000</code>\n"
        "• <code>/set sol above 100</code>\n"
        "• <code>/set bnb &lt; 500</code>\n\n"
        
        "⚠️ <b>Note:</b> Only top 200 CoinGecko coins are supported.\n\n"
        
        "💡 <b>Tip:</b> For advanced alerts (percent change, volume spikes, risk levels, technical indicators), "
        "use the interactive mode by typing <code>/set</code>"
    )
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)
